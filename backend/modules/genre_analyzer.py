"""Analyze genre distribution across a music collection and propose folder structure."""

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from backend.config import (
    FOLDER_MAPPING_PATH,
    LABEL_MAPPING_PATH,
    TARGET_FOLDER_COUNT,
)
from backend.modules.scanner import scan_directory, TrackInfo
from backend.modules.genre_parser import parse_genre
from backend.modules.ai_embeddings import group_genres_by_similarity

logger = logging.getLogger(__name__)


def analyze_genres(
    directory: str,
    use_embeddings: bool = True,
    target_folders: int = TARGET_FOLDER_COUNT,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    recursive: bool = True,
) -> Dict:
    """Scan a directory, count genre frequencies, and propose folder structure.

    Returns a summary dict with genre stats and proposed folder mapping.
    """
    # Step 1: Scan all files
    tracks = scan_directory(directory, progress_callback=progress_callback, recursive=recursive)

    # Step 2: Count genre frequencies
    genre_counter: Counter = Counter()
    label_genre_map: Dict[str, Counter] = {}  # label → Counter of genres

    for track in tracks:
        genres = parse_genre(track.genre_raw)
        for g in genres:
            genre_counter[g] += 1

        # Build label → genre mapping
        if track.label and genres:
            label = track.label.strip()
            if label:
                if label not in label_genre_map:
                    label_genre_map[label] = Counter()
                for g in genres:
                    label_genre_map[label][g] += 1

    # Step 3: Group genres
    genre_counts = dict(genre_counter)

    if use_embeddings and len(genre_counts) > target_folders:
        groups = group_genres_by_similarity(genre_counts, target_groups=target_folders)
    else:
        # Simple: each genre is its own folder (up to target)
        top_genres = genre_counter.most_common(target_folders)
        groups = {g: [g] for g, _ in top_genres}
        # Remaining go to "Other"
        remaining = [g for g in genre_counts if g not in groups]
        if remaining:
            groups["Other"] = remaining

    # Step 4: Build folder mapping (folder_name → [genres])
    folder_mapping: Dict[str, List[str]] = {}
    for leader, members in groups.items():
        # Use the leader (most popular) as folder name
        folder_name = _sanitize_folder_name(leader)
        folder_mapping[folder_name] = sorted(members)

    # Step 5: Build label mapping (label → primary genre)
    label_mapping: Dict[str, str] = {}
    for label, genre_counts_for_label in label_genre_map.items():
        most_common = genre_counts_for_label.most_common(1)
        if most_common:
            label_mapping[label] = most_common[0][0]

    # Step 6: Save mappings
    _save_json(FOLDER_MAPPING_PATH, folder_mapping)
    _save_json(LABEL_MAPPING_PATH, label_mapping)

    # Build summary
    top_genres_dict = dict(genre_counter.most_common(50))

    return {
        "total_tracks": len(tracks),
        "unique_genres": len(genre_counts),
        "proposed_folders": len(folder_mapping),
        "labels_mapped": len(label_mapping),
        "top_genres": top_genres_dict,
        "folder_mapping": folder_mapping,
    }


def _sanitize_folder_name(name: str) -> str:
    """Convert a genre name to a valid folder name."""
    # Replace characters not allowed in folder names
    invalid = '<>:"/\\|?*'
    result = name
    for ch in invalid:
        result = result.replace(ch, "_")
    return result.strip().strip(".")


def _save_json(path: Path, data) -> None:
    """Save data as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {path}")


def load_folder_mapping() -> Dict[str, List[str]]:
    """Load folder mapping from JSON file."""
    if FOLDER_MAPPING_PATH.exists():
        with open(FOLDER_MAPPING_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_label_mapping() -> Dict[str, str]:
    """Load label mapping from JSON file."""
    if LABEL_MAPPING_PATH.exists():
        with open(LABEL_MAPPING_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
