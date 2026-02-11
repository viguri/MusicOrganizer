"""Map a track to its destination style folder.

Classification cascade:
1. Genre ID3 tag → folder_mapping lookup
2. Source folder name → infer genre
3. Label → label_mapping lookup
4. Fallback → __REVISAR/
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from thefuzz import fuzz

from backend.config import UNCLASSIFIED_FOLDER
from backend.modules.genre_parser import parse_genre
from backend.modules.genre_analyzer import load_folder_mapping, load_label_mapping

logger = logging.getLogger(__name__)

# Cache mappings
_folder_mapping: Optional[Dict[str, List[str]]] = None
_label_mapping: Optional[Dict[str, str]] = None
_genre_to_folder: Optional[Dict[str, str]] = None


def _load_mappings():
    """Load and cache mappings, build reverse lookup."""
    global _folder_mapping, _label_mapping, _genre_to_folder

    _folder_mapping = load_folder_mapping()
    _label_mapping = load_label_mapping()

    # Build reverse: genre → folder
    _genre_to_folder = {}
    for folder, genres in _folder_mapping.items():
        for g in genres:
            _genre_to_folder[g.lower()] = folder


def _ensure_mappings():
    if _genre_to_folder is None:
        _load_mappings()


def reload_mappings():
    """Force reload mappings from disk."""
    _load_mappings()


def classify_track(
    genre_raw: Optional[str],
    source_folder: Optional[str],
    label: Optional[str],
) -> Tuple[str, str]:
    """Classify a track into a destination folder.

    Returns:
        (folder_name, strategy) where strategy is one of:
        "genre_id3", "source_folder", "label", "fuzzy", "unclassified"
    """
    _ensure_mappings()
    assert _genre_to_folder is not None
    assert _label_mapping is not None

    # Strategy 1: Genre ID3 tag
    if genre_raw:
        genres = parse_genre(genre_raw)
        for g in genres:
            folder = _genre_to_folder.get(g.lower())
            if folder:
                return folder, "genre_id3"

        # Try fuzzy match
        for g in genres:
            match = _fuzzy_match_genre(g)
            if match:
                return match, "fuzzy"

    # Strategy 2: Source folder name
    if source_folder:
        folder_lower = source_folder.lower().strip("_").strip()
        # Direct match against folder mapping keys
        for folder_name in (_folder_mapping or {}):
            if folder_lower == folder_name.lower() or folder_lower in folder_name.lower():
                return folder_name, "source_folder"
        # Check if source folder name matches any genre
        match = _genre_to_folder.get(folder_lower)
        if match:
            return match, "source_folder"

    # Strategy 3: Label mapping
    if label:
        genre_from_label = _label_mapping.get(label)
        if genre_from_label:
            folder = _genre_to_folder.get(genre_from_label.lower())
            if folder:
                return folder, "label"

    # Strategy 4: Unclassified
    return UNCLASSIFIED_FOLDER, "unclassified"


def _fuzzy_match_genre(genre: str, threshold: int = 80) -> Optional[str]:
    """Try fuzzy matching a genre against known genres."""
    _ensure_mappings()
    assert _genre_to_folder is not None

    best_score = 0
    best_folder = None

    for known_genre, folder in _genre_to_folder.items():
        score = fuzz.ratio(genre.lower(), known_genre)
        if score > best_score and score >= threshold:
            best_score = score
            best_folder = folder

    return best_folder
