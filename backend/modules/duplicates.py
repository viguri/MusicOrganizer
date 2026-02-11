"""Detect duplicate audio files by SHA-256 hash and metadata comparison."""

import hashlib
import logging
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.config import AUDIO_EXTENSIONS, HASH_CHUNK_SIZE, SCANNER_WORKERS

logger = logging.getLogger(__name__)


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
        workers = min(SCANNER_WORKERS, len(candidates))
        done = 0

        with ProcessPoolExecutor(max_workers=workers) as executor:
            for file_path, file_hash in executor.map(_compute_hash, candidates, chunksize=32):
                if not file_hash.startswith("error:"):
                    hash_map[file_hash].append(file_path)
                done += 1
                if progress_callback and (done % 50 == 0 or done == len(candidates)):
                    progress_callback(done, len(candidates))

    # Step 4: Filter to actual duplicates (hash groups with >1 file)
    hash_duplicates = []
    total_hash_files = 0
    for h, files in hash_map.items():
        if len(files) > 1:
            hash_duplicates.append({"hash": h[:16], "files": sorted(files)})
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
            metadata_duplicates.append({"key": key, "files": sorted(files)})
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


def _empty_result() -> Dict:
    return {
        "total_hash_groups": 0,
        "total_hash_files": 0,
        "total_meta_groups": 0,
        "total_meta_files": 0,
        "hash_duplicates": [],
        "metadata_duplicates": [],
    }
