"""Detect duplicate audio files by SHA-256 hash and metadata comparison."""

import hashlib
import logging
import os
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.config import AUDIO_EXTENSIONS, HASH_CHUNK_SIZE, SCANNER_WORKERS

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

    # Step 2: Group by file size (fast pre-filter)
    size_groups: Dict[int, List[str]] = defaultdict(list)
    for fp in all_files:
        try:
            size = os.path.getsize(fp)
            size_groups[size].append(fp)
        except OSError:
            pass

    # Only hash files that share a size with at least one other file
    candidates = []
    for size, files in size_groups.items():
        if len(files) > 1:
            candidates.extend(files)

    # Step 3: Compute hashes (only for size-matched candidates)
    hash_map: Dict[str, List[str]] = defaultdict(list)

    if candidates:
        # Use more workers for better parallelism (2x CPU count, capped at candidates)
        workers = min(SCANNER_WORKERS * 2, len(candidates), 32)
        done = 0

        with ProcessPoolExecutor(max_workers=workers) as executor:
            # Larger chunksize for better throughput
            chunksize = max(1, len(candidates) // (workers * 4))
            for file_path, file_hash in executor.map(_compute_hash, candidates, chunksize=chunksize):
                if not file_hash.startswith("error:"):
                    hash_map[file_hash].append(file_path)
                done += 1
                if progress_callback and (done % 50 == 0 or done == len(candidates)):
                    progress_callback(done, len(candidates))

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
    meta_groups: Dict[str, List[str]] = defaultdict(list)
    try:
        from backend.modules.scanner import _scan_single_file

        for fp in all_files:
            info = _scan_single_file(fp)
            if info.artist and info.title:
                key = f"{info.artist.lower().strip()} - {info.title.lower().strip()}"
                meta_groups[key].append(fp)
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
