"""Organize music files: plan moves (dry-run) and execute them.

Performance-optimized for large collections (15K+ files):
- os.rename() on same volume = O(1), no data copy
- Pre-create all destination folders before moving (single pass)
- ThreadPoolExecutor with high worker count for parallel I/O
- In-memory collision tracking to avoid per-file stat() calls
- Compact rollback JSON (no indent) for fast write
- Batched progress updates to minimize WebSocket overhead
"""

import json
import logging
import os
import shutil
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, Set

from backend.config import DATA_DIR, MOVER_WORKERS, UNCLASSIFIED_FOLDER
from backend.modules.scanner import scan_directory, TrackInfo
from backend.modules.genre_parser import parse_genre
from backend.modules.genre_mapper import classify_track

logger = logging.getLogger(__name__)

# Adaptive worker count: more workers for same-volume renames (I/O-free),
# fewer for cross-volume copies (I/O-bound, disk contention)
SAME_VOLUME_WORKERS = max(MOVER_WORKERS, 32)
CROSS_VOLUME_WORKERS = min(MOVER_WORKERS, 8)


def _same_volume(path_a: str, path_b: str) -> bool:
    """Check if two paths are on the same volume (drive letter on Windows, mount on Unix)."""
    try:
        if os.name == "nt":
            return os.path.splitdrive(path_a)[0].upper() == os.path.splitdrive(path_b)[0].upper()
        else:
            return os.stat(path_a).st_dev == os.stat(os.path.dirname(path_b)).st_dev
    except OSError:
        return False


@dataclass
class MoveItem:
    source: str
    dest: str
    folder: str
    genre_raw: str
    strategy: str
    file_name: str


@dataclass
class OrganizePlan:
    plan_id: str
    source: str
    dest: str
    moves: List[MoveItem]
    already_correct: int
    unclassified: int
    total_files: int
    files_to_move: int

    def to_dict(self) -> Dict:
        return {
            "plan_id": self.plan_id,
            "source": self.source,
            "dest": self.dest,
            "total_files": self.total_files,
            "files_to_move": self.files_to_move,
            "files_already_correct": self.already_correct,
            "files_unclassified": self.unclassified,
            "moves": [
                {
                    "source": m.source,
                    "dest": m.dest,
                    "folder": m.folder,
                    "genre_raw": m.genre_raw,
                    "strategy": m.strategy,
                    "file_name": m.file_name,
                }
                for m in self.moves
            ],
            "folder_summary": self._folder_summary(),
        }

    def _folder_summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for m in self.moves:
            counts[m.folder] = counts.get(m.folder, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))


def plan_organize(
    source: str,
    dest: str,
    recursive: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> OrganizePlan:
    """Scan source directory and plan file moves (dry-run).

    Args:
        source: Source directory to scan
        dest: Destination root (e.g. _STYLES/)
        recursive: If True, scan subdirectories recursively
        progress_callback: Called with (current, total)

    Returns:
        OrganizePlan with all proposed moves
    """
    import uuid

    tracks = scan_directory(source, progress_callback=progress_callback, recursive=recursive)
    plan_id = str(uuid.uuid4())[:8]

    moves: List[MoveItem] = []
    already_correct = 0
    unclassified = 0

    # Pre-resolve dest as absolute path once
    dest_abs = os.path.abspath(dest)

    for track in tracks:
        source_folder = Path(track.file_path).parent.name
        folder, strategy = classify_track(track.genre_raw, source_folder, track.label)

        dest_dir = os.path.join(dest_abs, folder)
        dest_path = os.path.join(dest_dir, track.file_name)

        # Check if already in correct location
        if os.path.dirname(os.path.abspath(track.file_path)) == dest_dir:
            already_correct += 1
            continue

        if folder == UNCLASSIFIED_FOLDER:
            unclassified += 1

        moves.append(MoveItem(
            source=track.file_path,
            dest=dest_path,
            folder=folder,
            genre_raw=track.genre_raw or "",
            strategy=strategy,
            file_name=track.file_name,
        ))

    plan = OrganizePlan(
        plan_id=plan_id,
        source=source,
        dest=dest,
        moves=moves,
        already_correct=already_correct,
        unclassified=unclassified,
        total_files=len(tracks),
        files_to_move=len(moves),
    )

    logger.info(
        f"Plan {plan_id}: {len(moves)} to move, {already_correct} correct, "
        f"{unclassified} unclassified out of {len(tracks)} total"
    )
    return plan


def execute_plan(
    plan: OrganizePlan,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict:
    """Execute a previously created organize plan.

    Performance optimizations:
    - Pre-creates all destination directories in a single pass
    - Uses os.rename() for same-volume moves (O(1), instant)
    - Falls back to shutil.copy2 + os.unlink for cross-volume
    - Tracks used filenames in-memory to avoid per-file stat() for collisions
    - Adaptive thread count: more for same-volume, fewer for cross-volume
    - Compact rollback JSON (no indent) for fast serialization
    """
    moves = plan.moves
    total = len(moves)

    if total == 0:
        return {"files_moved": 0, "files_failed": 0, "files_already_correct": plan.already_correct}

    t0 = time.perf_counter()

    # ── Phase 1: Write rollback log (compact, no indent) ──────────────────
    rollback_path = DATA_DIR / f"rollback_{plan.plan_id}.json"
    rollback_entries = [{"s": m.source, "d": m.dest} for m in moves]
    with open(rollback_path, "w", encoding="utf-8") as f:
        json.dump(rollback_entries, f, separators=(",", ":"), ensure_ascii=False)
    logger.info(f"Rollback log written: {rollback_path}")

    # ── Phase 2: Pre-create ALL destination directories ───────────────────
    dest_dirs: Set[str] = set()
    for m in moves:
        dest_dirs.add(os.path.dirname(m.dest))
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
    logger.info(f"Pre-created {len(dest_dirs)} destination directories")

    # ── Phase 3: Detect same-volume for adaptive worker count ─────────────
    is_same_vol = _same_volume(moves[0].source, moves[0].dest) if moves else True
    num_workers = SAME_VOLUME_WORKERS if is_same_vol else CROSS_VOLUME_WORKERS
    logger.info(f"Moving {total} files with {num_workers} workers (same_volume={is_same_vol})")

    # ── Phase 4: Move files in parallel ───────────────────────────────────
    moved = 0
    failed = 0
    errors: List[Dict] = []
    collision_lock = Lock()
    used_paths: Set[str] = set()  # Track used dest paths to avoid stat() calls

    def _move_file(item: MoveItem) -> Optional[str]:
        """Move a single file. Returns error string or None."""
        try:
            dest_path = item.dest

            # Thread-safe collision check using in-memory set
            with collision_lock:
                if dest_path in used_paths or os.path.exists(dest_path):
                    stem, ext = os.path.splitext(os.path.basename(dest_path))
                    parent = os.path.dirname(dest_path)
                    counter = 1
                    while True:
                        candidate = os.path.join(parent, f"{stem} ({counter}){ext}")
                        if candidate not in used_paths and not os.path.exists(candidate):
                            dest_path = candidate
                            break
                        counter += 1
                used_paths.add(dest_path)

            # Move: try rename first (O(1) same volume), then copy+delete
            try:
                os.rename(item.source, dest_path)
            except OSError:
                # Cross-volume: copy2 preserves metadata, then remove source
                shutil.copy2(item.source, dest_path)
                os.unlink(item.source)

            return None
        except Exception as e:
            return f"{item.source}: {e}"

    # Adaptive progress batch size: less frequent updates for large collections
    progress_batch = max(50, total // 100)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_move_file, m): m for m in moves}
        for i, future in enumerate(as_completed(futures)):
            error = future.result()
            if error:
                failed += 1
                if len(errors) < 50:
                    errors.append({"error": error})
            else:
                moved += 1

            if progress_callback and (i % progress_batch == 0 or i == total - 1):
                progress_callback(i + 1, total)

    elapsed = time.perf_counter() - t0
    rate = moved / elapsed if elapsed > 0 else 0
    logger.info(f"Execute: {moved} moved, {failed} failed in {elapsed:.1f}s ({rate:.0f} files/s)")

    return {
        "files_moved": moved,
        "files_failed": failed,
        "files_already_correct": plan.already_correct,
        "rollback_log": str(rollback_path),
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "files_per_second": round(rate, 0),
    }


def rollback(rollback_log_path: str) -> Dict:
    """Rollback moves using a rollback log file."""
    path = Path(rollback_log_path)
    if not path.exists():
        raise FileNotFoundError(f"Rollback log not found: {rollback_log_path}")

    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    restored = 0
    failed = 0

    for entry in entries:
        # Support both compact ("s"/"d") and legacy ("src"/"dst") keys
        src = entry.get("d") or entry.get("dst")  # Current location (was destination)
        dst = entry.get("s") or entry.get("src")  # Original location (was source)
        try:
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.rename(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                    os.unlink(src)
                restored += 1
        except Exception as e:
            logger.warning(f"Rollback failed for {src}: {e}")
            failed += 1

    logger.info(f"Rollback: {restored} restored, {failed} failed")
    return {"restored": restored, "failed": failed}


def create_folder_structure(dest: str) -> Dict:
    """Create all folders from folder_mapping.json in the destination directory."""
    from backend.modules.genre_analyzer import load_folder_mapping

    mapping = load_folder_mapping()
    dest_path = Path(dest)
    created = 0

    for folder_name in mapping:
        folder_path = dest_path / folder_name
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            created += 1

    # Always create __REVISAR
    revisar = dest_path / UNCLASSIFIED_FOLDER
    if not revisar.exists():
        revisar.mkdir(parents=True, exist_ok=True)
        created += 1

    return {"status": "ok", "folders_in_mapping": len(mapping), "folders_created": created}


def cleanup_empty_folders(directory: str) -> List[str]:
    """Remove empty folders recursively."""
    removed = []
    dir_path = Path(directory)

    # Walk bottom-up
    for root, dirs, files in os.walk(str(dir_path), topdown=False):
        for d in dirs:
            folder = Path(root) / d
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                    removed.append(str(folder))
            except OSError:
                pass

    logger.info(f"Cleaned up {len(removed)} empty folders in {directory}")
    return removed
