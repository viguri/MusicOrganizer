"""Detect duplicate audio files by SHA-256 hash and metadata comparison."""

import hashlib
import logging
import os
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from backend.config import (
    AUDIO_EXTENSIONS,
    HASH_CHUNK_SIZE,
    SCANNER_WORKERS,
    DUPLICATES_QUICK_HASH_BYTES,
    DUPLICATES_HASH_WORKERS,
    DUPLICATES_METADATA_WORKERS,
    DUPLICATES_MAX_WORKERS_CAP,
    DUPLICATES_STORAGE_MODE,
    DUPLICATES_METADATA_SIZE_TOLERANCE,
)
from backend.modules.database import get_db, get_hash_cache_entries, upsert_hash_cache_entries

logger = logging.getLogger(__name__)


def _get_file_priority(file_path: str) -> tuple:
    """Calculate priority for a file based on naming patterns.
    
    Files with suffixes like (1), (2), (3) get lower priority.
    Returns (priority, file_path) where lower priority number = keep this file.
    
    Priority levels:
    0 = Original file (no numeric suffix)
    1+ = Copy number (e.g., (1) = priority 1, (2) = priority 2)
    """
    filename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(filename)[0]
    
    # Match patterns like " (1)", " (2)", " (3)" at the end of filename
    match = re.search(r'\s*\((\d+)\)\s*$', name_without_ext)
    
    if match:
        copy_number = int(match.group(1))
        return (copy_number, file_path)
    
    # No suffix = original file, highest priority (0)
    return (0, file_path)


def _compute_hash(file_path: str) -> tuple:
    """Compute SHA-256 hash of a file. Returns (file_path, hash)."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return file_path, h.hexdigest()
    except Exception as e:
        return file_path, f"error:{e}"


def _compute_quick_hash(task: Tuple[str, int]) -> tuple:
    """Compute hash of the first N bytes. Returns (file_path, quick_hash)."""
    file_path, quick_bytes = task
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            chunk = f.read(max(1, quick_bytes))
            h.update(chunk)
        return file_path, h.hexdigest()
    except Exception as e:
        return file_path, f"error:{e}"


def _extract_metadata_key(file_path: str) -> tuple:
    """Extract normalized metadata key used for duplicate grouping."""
    try:
        from backend.modules.scanner import _scan_single_file

        info = _scan_single_file(file_path)
        if info and info.artist and info.title:
            key = f"{info.artist.lower().strip()} - {info.title.lower().strip()}"
            return file_path, key
        return file_path, None
    except Exception:
        return file_path, None


def _iter_chunks(values: List[str], size: int = 800):
    for idx in range(0, len(values), size):
        yield values[idx: idx + size]


def _storage_profile(source: str, against: Optional[str]) -> str:
    mode = DUPLICATES_STORAGE_MODE
    if mode in {"ssd", "hdd", "network"}:
        return mode

    candidate_paths = [p for p in (source, against) if p]
    if any(str(p).startswith("\\\\") for p in candidate_paths):
        return "network"
    return "ssd"


def _resolve_workers(
    total_items: int,
    storage_profile: str,
    configured: int,
    cpu_multiplier: int,
    hard_cap: int,
) -> int:
    if total_items <= 0:
        return 1

    if configured and configured > 0:
        return max(1, min(configured, total_items, hard_cap))

    if storage_profile == "network":
        base = max(2, min(SCANNER_WORKERS, 8))
    elif storage_profile == "hdd":
        base = max(2, SCANNER_WORKERS)
    else:
        base = max(2, SCANNER_WORKERS * cpu_multiplier)

    return max(1, min(base, total_items, hard_cap))


def _metadata_name_key(file_path: str) -> str:
    stem = Path(file_path).stem.lower()
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = re.sub(r"[^a-z0-9]+", "", stem)
    return stem


def _build_file_stats(file_paths: List[str]) -> Dict[str, Dict]:
    stats: Dict[str, Dict] = {}
    for fp in file_paths:
        try:
            file_stat = os.stat(fp)
            stats[fp] = {
                "size": int(file_stat.st_size),
                "mtime": float(file_stat.st_mtime),
            }
        except OSError:
            continue
    return stats


def find_duplicates(
    source: str,
    against: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict:
    """Find duplicate files by hash and metadata.

    Args:
        source: Primary directory to scan
        against: Optional second directory to compare against
        progress_callback: Called with (current, total)

    Returns:
        Dict with hash_duplicates, metadata_duplicates, and counts
    """
    # Step 1: Discover files
    source_files = _discover_files(source)
    against_files = _discover_files(against) if against else []
    all_files = source_files + against_files
    total = len(all_files)

    if total == 0:
        return _empty_result()

    # Step 2: Build file stats and group by file size (fast pre-filter)
    file_stats = _build_file_stats(all_files)
    size_groups: Dict[int, List[str]] = defaultdict(list)
    for fp, stat_info in file_stats.items():
        size_groups[stat_info["size"]].append(fp)

    # Only hash files that share a size with at least one other file
    candidates = []
    for size, files in size_groups.items():
        if len(files) > 1:
            candidates.extend(files)

    # Step 3: Compute hashes (two-phase: quick hash then full hash)
    hash_map: Dict[str, List[str]] = defaultdict(list)
    storage_profile = _storage_profile(source, against)
    cache_hits_quick = 0
    cache_hits_full = 0
    cache_writes: List[Dict] = []

    if candidates:
        cache_by_path: Dict[str, Dict] = {}
        with get_db() as conn:
            for chunk in _iter_chunks(candidates):
                cache_by_path.update(get_hash_cache_entries(conn, chunk))

        # Phase 3a: quick hash to reduce full-file hashing workload
        quick_hash_by_path: Dict[str, str] = {}
        quick_tasks: List[Tuple[str, int]] = []
        for fp in candidates:
            info = file_stats.get(fp)
            if not info:
                continue

            cached = cache_by_path.get(fp)
            if (
                cached
                and int(cached.get("file_size", -1)) == info["size"]
                and abs(float(cached.get("mtime", -1.0)) - info["mtime"]) < 1e-6
                and cached.get("quick_hash")
            ):
                quick_hash_by_path[fp] = str(cached["quick_hash"])
                cache_hits_quick += 1
            else:
                quick_tasks.append((fp, DUPLICATES_QUICK_HASH_BYTES))

        if quick_tasks:
            quick_workers = _resolve_workers(
                total_items=len(quick_tasks),
                storage_profile=storage_profile,
                configured=DUPLICATES_HASH_WORKERS,
                cpu_multiplier=2,
                hard_cap=max(1, DUPLICATES_MAX_WORKERS_CAP),
            )
            quick_chunksize = max(1, len(quick_tasks) // (quick_workers * 4))
            with ProcessPoolExecutor(max_workers=quick_workers) as executor:
                for file_path, quick_hash in executor.map(_compute_quick_hash, quick_tasks, chunksize=quick_chunksize):
                    if quick_hash.startswith("error:"):
                        continue
                    quick_hash_by_path[file_path] = quick_hash
                    info = file_stats.get(file_path)
                    if info:
                        cache_writes.append({
                            "file_path": file_path,
                            "file_size": info["size"],
                            "mtime": info["mtime"],
                            "quick_hash": quick_hash,
                            "full_hash": None,
                        })

        # Keep only groups with same size + same quick hash
        quick_groups: Dict[Tuple[int, str], List[str]] = defaultdict(list)
        for fp in candidates:
            quick_hash = quick_hash_by_path.get(fp)
            info = file_stats.get(fp)
            if quick_hash and info:
                quick_groups[(info["size"], quick_hash)].append(fp)

        full_candidates: List[str] = []
        for files in quick_groups.values():
            if len(files) > 1:
                full_candidates.extend(files)

        done = 0
        if full_candidates:
            full_hash_by_path: Dict[str, str] = {}
            full_tasks: List[str] = []

            for fp in full_candidates:
                info = file_stats.get(fp)
                cached = cache_by_path.get(fp)
                if (
                    info
                    and cached
                    and int(cached.get("file_size", -1)) == info["size"]
                    and abs(float(cached.get("mtime", -1.0)) - info["mtime"]) < 1e-6
                    and cached.get("full_hash")
                ):
                    full_hash_by_path[fp] = str(cached["full_hash"])
                    cache_hits_full += 1
                else:
                    full_tasks.append(fp)

            if full_tasks:
                full_workers = _resolve_workers(
                    total_items=len(full_tasks),
                    storage_profile=storage_profile,
                    configured=DUPLICATES_HASH_WORKERS,
                    cpu_multiplier=2,
                    hard_cap=max(1, DUPLICATES_MAX_WORKERS_CAP),
                )
                full_chunksize = max(1, len(full_tasks) // (full_workers * 4))
                with ProcessPoolExecutor(max_workers=full_workers) as executor:
                    for file_path, file_hash in executor.map(_compute_hash, full_tasks, chunksize=full_chunksize):
                        if file_hash.startswith("error:"):
                            continue
                        full_hash_by_path[file_path] = file_hash
                        info = file_stats.get(file_path)
                        if info:
                            cache_writes.append({
                                "file_path": file_path,
                                "file_size": info["size"],
                                "mtime": info["mtime"],
                                "quick_hash": quick_hash_by_path.get(file_path),
                                "full_hash": file_hash,
                            })
                        done += 1
                        if progress_callback and (done % 50 == 0 or done == len(full_tasks)):
                            progress_callback(done, len(full_tasks))

            for fp in full_candidates:
                file_hash = full_hash_by_path.get(fp)
                if file_hash:
                    hash_map[file_hash].append(fp)

        if cache_writes:
            dedup_cache_writes: Dict[str, Dict] = {}
            for entry in cache_writes:
                dedup_cache_writes[entry["file_path"]] = entry
            with get_db() as conn:
                upsert_hash_cache_entries(conn, list(dedup_cache_writes.values()))

    # Step 4: Filter to actual duplicates (hash groups with >1 file)
    # Sort files by priority: originals first, then copies (1), (2), etc.
    hash_duplicates = []
    total_hash_files = 0
    for h, files in hash_map.items():
        if len(files) > 1:
            # Sort by priority: (0, path) for originals, (1, path) for (1), etc.
            sorted_files = [fp for _, fp in sorted(_get_file_priority(fp) for fp in files)]
            
            # Mark which files to keep vs delete
            files_info = []
            for idx, fp in enumerate(sorted_files):
                priority, _ = _get_file_priority(fp)
                files_info.append({
                    "path": fp,
                    "action": "keep" if idx == 0 else "delete",
                    "reason": "original" if priority == 0 else f"copy ({priority})"
                })
            
            hash_duplicates.append({
                "hash": h[:16],
                "files": sorted_files,
                "files_info": files_info
            })
            total_hash_files += len(files)

    # Step 5: Metadata-based duplicates (artist + title)
    # Narrow candidates before metadata parsing using filename and size heuristics.
    meta_groups: Dict[str, List[str]] = defaultdict(list)
    try:
        filename_groups: Dict[str, List[str]] = defaultdict(list)
        for fp in all_files:
            filename_groups[_metadata_name_key(fp)].append(fp)

        metadata_candidates: Set[str] = set()
        for files in filename_groups.values():
            if len(files) > 1:
                metadata_candidates.update(files)

        # Include exact same-size groups to avoid missing differently named duplicates.
        for files in size_groups.values():
            if len(files) > 1:
                metadata_candidates.update(files)

        candidate_list = sorted(metadata_candidates) if metadata_candidates else list(all_files)
        if not candidate_list:
            candidate_list = list(all_files)

        # Optional size narrowing inside metadata phase.
        size_tolerance = max(0.0, DUPLICATES_METADATA_SIZE_TOLERANCE)
        if size_tolerance > 0 and file_stats:
            by_name_candidates: Dict[str, List[str]] = defaultdict(list)
            for fp in candidate_list:
                by_name_candidates[_metadata_name_key(fp)].append(fp)

            narrowed_set: Set[str] = set()
            for files in by_name_candidates.values():
                if len(files) < 2:
                    continue
                sorted_files = sorted(files, key=lambda f: file_stats.get(f, {}).get("size", 0))
                for idx, left_fp in enumerate(sorted_files):
                    left_size = max(1, int(file_stats.get(left_fp, {}).get("size", 0)))
                    for right_fp in sorted_files[idx + 1:]:
                        right_size = max(1, int(file_stats.get(right_fp, {}).get("size", 0)))
                        rel_diff = abs(left_size - right_size) / max(left_size, right_size)
                        if rel_diff <= size_tolerance:
                            narrowed_set.add(left_fp)
                            narrowed_set.add(right_fp)

            narrowed = sorted(narrowed_set)
            if narrowed:
                candidate_list = narrowed

        metadata_workers = _resolve_workers(
            total_items=len(candidate_list),
            storage_profile=storage_profile,
            configured=DUPLICATES_METADATA_WORKERS,
            cpu_multiplier=1,
            hard_cap=max(1, DUPLICATES_MAX_WORKERS_CAP),
        )

        metadata_chunksize = max(1, len(candidate_list) // max(1, metadata_workers * 4))
        with ProcessPoolExecutor(max_workers=metadata_workers) as executor:
            for file_path, key in executor.map(_extract_metadata_key, candidate_list, chunksize=metadata_chunksize):
                if key:
                    meta_groups[key].append(file_path)
    except Exception as e:
        logger.warning(f"Metadata duplicate scan failed: {e}")

    metadata_duplicates = []
    total_meta_files = 0
    for key, files in meta_groups.items():
        if len(files) > 1:
            # Sort by priority: originals first, then copies (1), (2), etc.
            sorted_files = [fp for _, fp in sorted(_get_file_priority(fp) for fp in files)]
            
            # Mark which files to keep vs delete
            files_info = []
            for idx, fp in enumerate(sorted_files):
                priority, _ = _get_file_priority(fp)
                files_info.append({
                    "path": fp,
                    "action": "keep" if idx == 0 else "delete",
                    "reason": "original" if priority == 0 else f"copy ({priority})"
                })
            
            metadata_duplicates.append({
                "key": key,
                "files": sorted_files,
                "files_info": files_info
            })
            total_meta_files += len(files)

    return {
        "total_hash_groups": len(hash_duplicates),
        "total_hash_files": total_hash_files,
        "total_meta_groups": len(metadata_duplicates),
        "total_meta_files": total_meta_files,
        "performance": {
            "storage_profile": storage_profile,
            "hash_candidates": len(candidates),
            "cache_hits_quick": cache_hits_quick,
            "cache_hits_full": cache_hits_full,
        },
        "hash_duplicates": hash_duplicates,
        "metadata_duplicates": metadata_duplicates,
    }


def _discover_files(directory: Optional[str]) -> List[str]:
    """Discover audio files in a directory."""
    if not directory or not Path(directory).is_dir():
        return []
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                files.append(os.path.join(root, fname))
    return files


def move_duplicates(
    duplicate_result: Dict,
    destination_folder: str,
    use_hash: bool = True,
    use_metadata: bool = False,
    dry_run: bool = True,
    preserve_structure: bool = True
) -> Dict:
    """Move duplicate files to a quarantine folder instead of deleting them.
    
    Args:
        duplicate_result: Result from find_duplicates()
        destination_folder: Folder where duplicates will be moved
        use_hash: Move hash-based duplicates
        use_metadata: Move metadata-based duplicates
        dry_run: If True, only report what would be moved
        preserve_structure: If True, preserve original directory structure
    
    Returns:
        Dict with move results
    """
    import shutil
    from datetime import datetime
    
    files_to_move = []
    
    # Collect files marked for deletion from hash duplicates
    if use_hash:
        for group in duplicate_result.get("hash_duplicates", []):
            for file_info in group.get("files_info", []):
                if file_info["action"] == "delete":
                    files_to_move.append({
                        "path": file_info["path"],
                        "reason": file_info["reason"],
                        "type": "hash"
                    })
    
    # Collect files marked for deletion from metadata duplicates
    if use_metadata:
        for group in duplicate_result.get("metadata_duplicates", []):
            for file_info in group.get("files_info", []):
                if file_info["action"] == "delete":
                    # Avoid moving the same file twice
                    if not any(f["path"] == file_info["path"] for f in files_to_move):
                        files_to_move.append({
                            "path": file_info["path"],
                            "reason": file_info["reason"],
                            "type": "metadata"
                        })
    
    moved = []
    errors = []
    
    if not dry_run:
        # Create destination folder with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_base = Path(destination_folder) / f"duplicates_{timestamp}"
        dest_base.mkdir(parents=True, exist_ok=True)
        
        for file_info in files_to_move:
            try:
                source_path = Path(file_info["path"])
                
                if preserve_structure:
                    # Preserve original directory structure
                    # Get relative path from root drive
                    try:
                        # Try to get relative path from common ancestor
                        rel_path = source_path.relative_to(source_path.anchor)
                    except ValueError:
                        # Fallback: use just the filename
                        rel_path = source_path.name
                    
                    dest_path = dest_base / rel_path
                else:
                    # Flat structure: all files in destination folder
                    dest_path = dest_base / source_path.name
                
                # Handle filename conflicts
                if dest_path.exists():
                    stem = dest_path.stem
                    suffix = dest_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = dest_path.parent / f"{stem}_{counter}{suffix}"
                        counter += 1
                
                # Create parent directories
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Move the file
                shutil.move(str(source_path), str(dest_path))
                
                move_info = {
                    **file_info,
                    "destination": str(dest_path)
                }
                moved.append(move_info)
                logger.info(f"Moved duplicate: {file_info['path']} -> {dest_path}")
                
            except Exception as e:
                error_info = {**file_info, "error": str(e)}
                errors.append(error_info)
                logger.error(f"Failed to move {file_info['path']}: {e}")
    
    return {
        "dry_run": dry_run,
        "total_to_move": len(files_to_move),
        "total_moved": len(moved),
        "total_errors": len(errors),
        "files_to_move": files_to_move if dry_run else moved,
        "errors": errors,
        "destination_folder": destination_folder if dry_run else str(dest_base) if not dry_run and moved else None
    }


def delete_duplicates(
    duplicate_result: Dict,
    use_hash: bool = True,
    use_metadata: bool = False,
    dry_run: bool = True
) -> Dict:
    """Delete duplicate files based on priority.
    
    Args:
        duplicate_result: Result from find_duplicates()
        use_hash: Delete hash-based duplicates
        use_metadata: Delete metadata-based duplicates
        dry_run: If True, only report what would be deleted
    
    Returns:
        Dict with deletion results
    """
    files_to_delete = []
    
    # Collect files marked for deletion from hash duplicates
    if use_hash:
        for group in duplicate_result.get("hash_duplicates", []):
            for file_info in group.get("files_info", []):
                if file_info["action"] == "delete":
                    files_to_delete.append({
                        "path": file_info["path"],
                        "reason": file_info["reason"],
                        "type": "hash"
                    })
    
    # Collect files marked for deletion from metadata duplicates
    if use_metadata:
        for group in duplicate_result.get("metadata_duplicates", []):
            for file_info in group.get("files_info", []):
                if file_info["action"] == "delete":
                    # Avoid deleting the same file twice
                    if not any(f["path"] == file_info["path"] for f in files_to_delete):
                        files_to_delete.append({
                            "path": file_info["path"],
                            "reason": file_info["reason"],
                            "type": "metadata"
                        })
    
    deleted = []
    errors = []
    
    if not dry_run:
        for file_info in files_to_delete:
            try:
                os.remove(file_info["path"])
                deleted.append(file_info)
                logger.info(f"Deleted duplicate: {file_info['path']}")
            except Exception as e:
                error_info = {**file_info, "error": str(e)}
                errors.append(error_info)
                logger.error(f"Failed to delete {file_info['path']}: {e}")
    
    return {
        "dry_run": dry_run,
        "total_to_delete": len(files_to_delete),
        "total_deleted": len(deleted),
        "total_errors": len(errors),
        "files_to_delete": files_to_delete if dry_run else deleted,
        "errors": errors
    }


def _empty_result() -> Dict:
    return {
        "total_hash_groups": 0,
        "total_hash_files": 0,
        "total_meta_groups": 0,
        "total_meta_files": 0,
        "hash_duplicates": [],
        "metadata_duplicates": [],
    }
