"""Map a track to its destination style folder.

Classification cascade:
1. Genre ID3 tag → folder_mapping lookup
2. Source folder name → infer genre
3. Label → label_mapping lookup
4. Fallback → __REVISAR/
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

from thefuzz import fuzz

from backend.config import OTHER_FOLDER, UNCLASSIFIED_FOLDER
from backend.modules.genre_parser import parse_genre, is_valid_genre_name, sanitize_folder_name
from backend.modules.genre_analyzer import load_folder_mapping, load_label_mapping

logger = logging.getLogger(__name__)

_ROOT_GENRES = [
    "House",
    "Techno",
    "Trance",
    "Progressive",
    "Minimal",
    "Electro",
    "Breaks",
    "Dubstep",
    "Drum & Bass",
    "Hip-Hop",
    "Ambient",
]

# Cache mappings
_folder_mapping: Optional[Dict[str, List[str]]] = None
_label_mapping: Optional[Dict[str, str]] = None
_genre_to_folder: Optional[Dict[str, str]] = None


def _load_mappings():
    """Load and cache mappings, build reverse lookup."""
    global _folder_mapping, _label_mapping, _genre_to_folder

    raw_mapping = load_folder_mapping()
    _folder_mapping = {}

    # Sanitize folder names from mapping and merge on collisions
    for folder, genres in raw_mapping.items():
        safe_folder = sanitize_folder_name(folder, fallback=OTHER_FOLDER)
        _folder_mapping.setdefault(safe_folder, []).extend(genres)

    for folder, genres in list(_folder_mapping.items()):
        _folder_mapping[folder] = sorted(set(genres))

    # Ensure fallback bucket exists
    _folder_mapping.setdefault(OTHER_FOLDER, [])
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


def _infer_hierarchical_folder(base_folder: str, genre_name: str) -> str:
    """Infer parent/subfolder path from a genre label.

    Examples:
        "Techno Peak Time" -> "Techno/Peak Time"
        "Afro House" -> "House/Afro House"
    """
    safe_base = sanitize_folder_name(base_folder, fallback=OTHER_FOLDER)
    safe_genre = sanitize_folder_name(genre_name, fallback=safe_base)

    # Build candidate parents from known roots + mapping folders
    mapping_keys = list((_folder_mapping or {}).keys())
    candidate_parents = []
    for root in _ROOT_GENRES + mapping_keys:
        safe_root = sanitize_folder_name(root, fallback="")
        if safe_root and safe_root not in candidate_parents:
            candidate_parents.append(safe_root)

    genre_lower = safe_genre.lower()

    for parent in candidate_parents:
        parent_lower = parent.lower()
        if genre_lower == parent_lower:
            return parent

        # Prefix style: "Techno Peak Time" => Techno/Peak Time
        if genre_lower.startswith(parent_lower + " "):
            child = safe_genre[len(parent):].strip(" -_/.")
            child_safe = sanitize_folder_name(child, fallback="")
            if child_safe:
                return os.path.join(parent, child_safe)

        # Suffix style: "Afro House" => House/Afro House
        if genre_lower.endswith(" " + parent_lower):
            return os.path.join(parent, safe_genre)

    return safe_base


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
        genres = [g for g in parse_genre(genre_raw) if is_valid_genre_name(g)]
        for g in genres:
            folder = _genre_to_folder.get(g.lower())
            if folder:
                final_folder = _infer_hierarchical_folder(folder, g)
                return final_folder, "genre_id3"

        # Try fuzzy match
        for g in genres:
            match = _fuzzy_match_genre(g)
            if match:
                final_folder = _infer_hierarchical_folder(match, g)
                return final_folder, "fuzzy"

        # Genre present but none is recognized -> Other
        if genres:
            return OTHER_FOLDER, "invalid_genre"

    # Strategy 2: Source folder name
    if source_folder:
        folder_lower = source_folder.lower().strip("_").strip()
        # Direct match against folder mapping keys
        for folder_name in (_folder_mapping or {}):
            if folder_lower == folder_name.lower() or folder_lower in folder_name.lower():
                return sanitize_folder_name(folder_name, fallback=OTHER_FOLDER), "source_folder"
        # Check if source folder name matches any genre
        match = _genre_to_folder.get(folder_lower)
        if match:
            return sanitize_folder_name(match, fallback=OTHER_FOLDER), "source_folder"

    # Strategy 3: Label mapping
    if label:
        genre_from_label = _label_mapping.get(label)
        if genre_from_label:
            folder = _genre_to_folder.get(genre_from_label.lower())
            if folder:
                return sanitize_folder_name(folder, fallback=OTHER_FOLDER), "label"

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
