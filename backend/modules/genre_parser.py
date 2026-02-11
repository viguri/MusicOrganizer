"""Parse and normalize genre strings from ID3 tags."""

import re
from typing import List

# Common separators in genre tags
_SEPARATORS = re.compile(r"[;,/&|]+")

# Patterns to strip
_STRIP_PATTERNS = [
    re.compile(r"\(.*?\)"),   # parenthetical notes
    re.compile(r"\[.*?\]"),   # bracketed notes
]

# CamelCase splitter: "DeepHouse" → "Deep House"
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")

# Normalization map for common variations
_NORMALIZE_MAP = {
    "drum n bass": "Drum & Bass",
    "drum and bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "d&b": "Drum & Bass",
    "deep tech": "Deep Tech House",
    "prog house": "Progressive House",
    "prog trance": "Progressive Trance",
    "electronica": "Electronic",
    "edm": "Electronic",
    "hiphop": "Hip-Hop",
    "hip hop": "Hip-Hop",
    "r&b": "R&B",
    "rnb": "R&B",
    "triphop": "Trip-Hop",
    "trip hop": "Trip-Hop",
    "lofi": "Lo-Fi",
    "lo fi": "Lo-Fi",
}


def parse_genre(raw: str | None) -> List[str]:
    """Parse a raw genre string into a list of normalized genre names.

    Handles:
    - Multiple separators: "House; Techno" → ["House", "Techno"]
    - CamelCase: "DeepHouse" → ["Deep House"]
    - Common abbreviations: "DnB" → ["Drum & Bass"]
    - Parenthetical/bracket removal
    """
    if not raw or not raw.strip():
        return []

    # Split by separators
    parts = _SEPARATORS.split(raw)
    genres = []

    for part in parts:
        g = part.strip()
        if not g:
            continue

        # Remove parenthetical/bracket content
        for pat in _STRIP_PATTERNS:
            g = pat.sub("", g).strip()

        if not g:
            continue

        # Split CamelCase
        g = _CAMEL.sub(" ", g)

        # Normalize whitespace
        g = " ".join(g.split())

        # Check normalization map
        key = g.lower().strip()
        if key in _NORMALIZE_MAP:
            g = _NORMALIZE_MAP[key]
        else:
            # Title case
            g = g.title()

        if g and g not in genres:
            genres.append(g)

    return genres


def normalize_genre(genre: str) -> str:
    """Normalize a single genre string."""
    result = parse_genre(genre)
    return result[0] if result else genre.strip().title()
