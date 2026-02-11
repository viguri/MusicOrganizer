"""Organize music files: plan moves (dry-run) and execute them.

Uses ThreadPoolExecutor for I/O-bound file moves.
os.rename() on the same volume is O(1) — no data copy.
"""

import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.config import DATA_DIR, MOVER_WORKERS, UNCLASSIFIED_FOLDER
from backend.modules.scanner import scan_directory, TrackInfo
from backend.modules.genre_parser import parse_genre
from backend.modules.genre_mapper import classify_track

logger = logging.getLogger(__name__)


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
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> OrganizePlan:
    """Scan source directory and plan file moves (dry-run).

    Args:
        source: Source directory to scan
        dest: Destination root (e.g. _STYLES/)
        progress_callback: Called with (current, total)

    Returns:
        OrganizePlan with all proposed moves
    """
    import uuid

    tracks = scan_directory(source, progress_callback=progress_callback)
    plan_id = str(uuid.uuid4())[:8]

    moves: List[MoveItem] = []
    already_correct = 0
    unclassified = 0

    for track in tracks:
        source_folder = Path(track.file_path).parent.name
        folder, strategy = classify_track(track.genre_raw, source_folder, track.label)

        dest_dir = Path(dest) / folder
        dest_path = dest_dir / track.file_name

        # Check if already in correct location
        if Path(track.file_path).parent == dest_dir:
            already_correct += 1
            continue

        if folder == UNCLASSIFIED_FOLDER:
            unclassified += 1

        moves.append(MoveItem(
            source=track.file_path,
            dest=str(dest_path),
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

    Creates a rollback log before moving files.
    Uses ThreadPoolExecutor for parallel I/O.
    """
    moves = plan.moves
    total = len(moves)

    if total == 0:
        return {"files_moved": 0, "files_failed": 0, "files_already_correct": plan.already_correct}

    # Write rollback log
    rollback_path = DATA_DIR / f"rollback_{plan.plan_id}.json"
    rollback_entries = [{"src": m.source, "dst": m.dest} for m in moves]
    with open(rollback_path, "w", encoding="utf-8") as f:
        json.dump(rollback_entries, f, indent=2, ensure_ascii=False)
    logger.info(f"Rollback log: {rollback_path}")

    moved = 0
    failed = 0
    errors: List[Dict] = []

    def _move_file(item: MoveItem) -> Optional[str]:
        """Move a single file. Returns error string or None."""
        try:
            dest_dir = Path(item.dest).parent
            dest_dir.mkdir(parents=True, exist_ok=True)

            dest_path = Path(item.dest)
            # Handle name collision
            if dest_path.exists():
                stem = dest_path.stem
                ext = dest_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = dest_dir / f"{stem} ({counter}){ext}"
                    counter += 1

            # Try rename first (instant on same volume), fall back to shutil.move
            try:
                os.rename(item.source, str(dest_path))
            except OSError:
                shutil.move(item.source, str(dest_path))

            return None
        except Exception as e:
            return f"{item.source}: {e}"

    with ThreadPoolExecutor(max_workers=MOVER_WORKERS) as executor:
        futures = {executor.submit(_move_file, m): m for m in moves}
        for i, future in enumerate(as_completed(futures)):
            error = future.result()
            if error:
                failed += 1
                errors.append({"error": error})
            else:
                moved += 1

            if progress_callback and (i % 20 == 0 or i == total - 1):
                progress_callback(i + 1, total)

    logger.info(f"Execute: {moved} moved, {failed} failed")

    return {
        "files_moved": moved,
        "files_failed": failed,
        "files_already_correct": plan.already_correct,
        "rollback_log": str(rollback_path),
        "errors": errors[:50],  # Limit error list
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
        src = entry["dst"]  # Current location (was destination)
        dst = entry["src"]  # Original location (was source)
        try:
            if Path(src).exists():
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.rename(src, dst)
                except OSError:
                    shutil.move(src, dst)
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
