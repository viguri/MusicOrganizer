"""Audio file scanner using mutagen for ID3 metadata reading.

Uses multiprocessing.Pool for parallel scanning of large collections.
"""

import logging
import os
import multiprocessing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from backend.config import AUDIO_EXTENSIONS, SCANNER_WORKERS, SCANNER_CHUNKSIZE

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    """Metadata extracted from an audio file."""
    file_path: str
    file_name: str
    file_extension: str
    file_size: int
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    genre_raw: Optional[str] = None
    label: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    duration: Optional[float] = None
    year: Optional[int] = None
    error: Optional[str] = None


def discover_audio_files(directory: str, recursive: bool = True) -> List[str]:
    """Walk a directory and return all audio file paths.

    Args:
        directory: Root directory to scan
        recursive: If True, scan subdirectories recursively. If False, only scan the top-level directory.
    """
    files = []
    if recursive:
        for root, _dirs, filenames in os.walk(directory):
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in AUDIO_EXTENSIONS:
                    files.append(os.path.join(root, fname))
    else:
        for fname in os.listdir(directory):
            full = os.path.join(directory, fname)
            if os.path.isfile(full):
                ext = os.path.splitext(fname)[1].lower()
                if ext in AUDIO_EXTENSIONS:
                    files.append(full)
    logger.info(f"Discovered {len(files)} audio files in {directory} (recursive={recursive})")
    return files


def _scan_single_file(file_path: str) -> TrackInfo:
    """Scan a single audio file for metadata. Runs in worker process."""
    try:
        import mutagen
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3
        from mutagen.flac import FLAC
        from mutagen.mp4 import MP4
        from mutagen.oggvorbis import OggVorbis
        from mutagen.aiff import AIFF

        p = Path(file_path)
        info = TrackInfo(
            file_path=str(p),
            file_name=p.name,
            file_extension=p.suffix.lower(),
            file_size=p.stat().st_size,
        )

        ext = p.suffix.lower()
        audio = None

        if ext == ".mp3":
            audio = MP3(file_path, ID3=EasyID3)
        elif ext == ".flac":
            audio = FLAC(file_path)
        elif ext in (".m4a", ".mp4"):
            audio = MP4(file_path)
        elif ext == ".ogg":
            audio = OggVorbis(file_path)
        elif ext in (".aiff", ".aif"):
            audio = AIFF(file_path)
        elif ext == ".wav":
            audio = mutagen.File(file_path)
        else:
            audio = mutagen.File(file_path, easy=True)

        if audio is None:
            info.error = "Could not read file"
            return info

        # Duration
        if hasattr(audio, "info") and audio.info:
            info.duration = getattr(audio.info, "length", None)

        # Extract tags — handle MP4 differently
        if ext in (".m4a", ".mp4") and isinstance(audio, MP4):
            tags = audio.tags or {}
            info.artist = _first(tags.get("\xa9ART"))
            info.title = _first(tags.get("\xa9nam"))
            info.album = _first(tags.get("\xa9alb"))
            info.genre_raw = _first(tags.get("\xa9gen"))
            info.year = _parse_year(_first(tags.get("\xa9day")))
            bpm_val = _first(tags.get("tmpo"))
            if bpm_val is not None:
                try:
                    info.bpm = float(bpm_val)
                except (ValueError, TypeError):
                    pass
        else:
            # EasyID3 / Vorbis / FLAC style
            tags = audio.tags or audio
            if hasattr(tags, "get"):
                info.artist = _first(tags.get("artist"))
                info.title = _first(tags.get("title"))
                info.album = _first(tags.get("album"))
                info.genre_raw = _first(tags.get("genre"))
                info.label = _first(tags.get("organization")) or _first(tags.get("publisher"))
                info.key = _first(tags.get("initialkey")) or _first(tags.get("key"))
                info.year = _parse_year(_first(tags.get("date")) or _first(tags.get("year")))
                bpm_str = _first(tags.get("bpm"))
                if bpm_str:
                    try:
                        info.bpm = float(bpm_str)
                    except (ValueError, TypeError):
                        pass

        return info

    except Exception as e:
        return TrackInfo(
            file_path=file_path,
            file_name=Path(file_path).name,
            file_extension=Path(file_path).suffix.lower(),
            file_size=Path(file_path).stat().st_size if Path(file_path).exists() else 0,
            error=str(e),
        )


def _first(val) -> Optional[str]:
    """Extract first value from a tag list or return the value itself."""
    if val is None:
        return None
    if isinstance(val, list):
        return str(val[0]) if val else None
    return str(val)


def _parse_year(val: Optional[str]) -> Optional[int]:
    """Parse a year from a date string."""
    if not val:
        return None
    try:
        return int(str(val)[:4])
    except (ValueError, TypeError):
        return None


def scan_directory(
    directory: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    workers: Optional[int] = None,
    recursive: bool = True,
) -> List[TrackInfo]:
    """Scan all audio files in a directory using multiprocessing.

    Args:
        directory: Path to scan
        progress_callback: Called with (current, total) for progress updates
        workers: Number of worker processes (default: SCANNER_WORKERS)

    Returns:
        List of TrackInfo objects
    """
    file_paths = discover_audio_files(directory, recursive=recursive)
    total = len(file_paths)

    if total == 0:
        return []

    num_workers = workers or SCANNER_WORKERS
    results: List[TrackInfo] = []

    # Use multiprocessing for large collections, single-process for small ones
    if total > 100 and num_workers > 1:
        with multiprocessing.Pool(num_workers) as pool:
            for i, result in enumerate(
                pool.imap_unordered(_scan_single_file, file_paths, chunksize=SCANNER_CHUNKSIZE)
            ):
                results.append(result)
                if progress_callback and (i % 50 == 0 or i == total - 1):
                    progress_callback(i + 1, total)
    else:
        for i, fp in enumerate(file_paths):
            results.append(_scan_single_file(fp))
            if progress_callback and (i % 10 == 0 or i == total - 1):
                progress_callback(i + 1, total)

    errors = sum(1 for r in results if r.error)
    logger.info(f"Scanned {total} files ({errors} errors) in {directory}")
    return results
