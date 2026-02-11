"""Clean audio file names: remove URL spam, numeric prefixes, normalize."""

import logging
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.config import AUDIO_EXTENSIONS

logger = logging.getLogger(__name__)

# URL patterns to remove
_URL_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?[\w.-]+\.(?:com|net|org|ru|info|co|io|me|cc|top)", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?djsoundtop\.com\]?", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?electronicfresh\.com\]?", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?beatport\.com\]?", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?traxsource\.com\]?", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?soundcloud\.com\]?", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?promodj\.com\]?", re.IGNORECASE),
    re.compile(r"\[?(?:www\.)?zippyshare\.com\]?", re.IGNORECASE),
]

# Numeric prefix: "01.", "02 -", "60.", etc.
_NUMERIC_PREFIX = re.compile(r"^\d{1,3}[\.\-\s_]+")

# Bracket/parenthesis spam
_BRACKET_SPAM = re.compile(r"\[(?:www\.|https?://)[^\]]*\]", re.IGNORECASE)
_PAREN_SPAM = re.compile(r"\((?:www\.|https?://)[^\)]*\)", re.IGNORECASE)

# Multiple spaces/dashes/underscores
_MULTI_SPACE = re.compile(r"\s{2,}")
_MULTI_DASH = re.compile(r"-{2,}")
_MULTI_UNDERSCORE = re.compile(r"_{2,}")

# Leading/trailing separators
_LEADING_SEP = re.compile(r"^[\s\-_\.]+")
_TRAILING_SEP = re.compile(r"[\s\-_\.]+$")


def clean_filename(name: str) -> str:
    """Clean a single filename (without extension).

    Removes URL spam, numeric prefixes, normalizes whitespace/separators.
    """
    cleaned = name

    # Remove bracket/paren spam first
    cleaned = _BRACKET_SPAM.sub("", cleaned)
    cleaned = _PAREN_SPAM.sub("", cleaned)

    # Remove URL patterns
    for pat in _URL_PATTERNS:
        cleaned = pat.sub("", cleaned)

    # Remove numeric prefix
    cleaned = _NUMERIC_PREFIX.sub("", cleaned)

    # Normalize separators
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    cleaned = _MULTI_DASH.sub("-", cleaned)
    cleaned = _MULTI_UNDERSCORE.sub("_", cleaned)

    # Clean leading/trailing separators
    cleaned = _LEADING_SEP.sub("", cleaned)
    cleaned = _TRAILING_SEP.sub("", cleaned)

    # Final trim
    cleaned = cleaned.strip()

    return cleaned if cleaned else name


def clean_directory(
    directory: str,
    dry_run: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict:
    """Clean all audio filenames in a directory.

    Args:
        directory: Path to scan
        dry_run: If True, only report changes without renaming
        progress_callback: Called with (current, total)

    Returns:
        Dict with total_renamed, dry_run flag, and list of changes
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    # Discover files
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                files.append(os.path.join(root, fname))

    total = len(files)
    changes: List[Dict] = []
    renamed = 0

    for i, file_path in enumerate(files):
        p = Path(file_path)
        stem = p.stem
        ext = p.suffix

        cleaned_stem = clean_filename(stem)

        if cleaned_stem != stem:
            new_name = cleaned_stem + ext
            new_path = p.parent / new_name

            change = {
                "original": p.name,
                "cleaned": new_name,
                "path": str(p.parent),
            }

            if not dry_run:
                # Handle name collision
                if new_path.exists() and new_path != p:
                    counter = 1
                    while new_path.exists():
                        new_name = f"{cleaned_stem} ({counter}){ext}"
                        new_path = p.parent / new_name
                        counter += 1
                    change["cleaned"] = new_name

                try:
                    os.rename(file_path, str(new_path))
                    renamed += 1
                except OSError as e:
                    change["error"] = str(e)
                    logger.warning(f"Failed to rename {file_path}: {e}")
            else:
                renamed += 1

            changes.append(change)

        if progress_callback and (i % 20 == 0 or i == total - 1):
            progress_callback(i + 1, total)

    logger.info(f"Name cleaning: {renamed} files {'would be' if dry_run else ''} renamed in {directory}")

    return {
        "total_renamed": renamed,
        "dry_run": dry_run,
        "changes": changes,
    }
