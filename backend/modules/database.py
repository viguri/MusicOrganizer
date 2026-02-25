"""SQLite database for music inventory."""

import sqlite3
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import DATABASE_PATH

logger = logging.getLogger(__name__)

CREATE_TRACKS_TABLE = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_extension TEXT,
    file_size INTEGER,
    file_hash TEXT,
    genre_raw TEXT,
    genre_normalized TEXT,
    genres_parsed TEXT,
    artist TEXT,
    title TEXT,
    album TEXT,
    label TEXT,
    bpm REAL,
    key TEXT,
    duration REAL,
    year INTEGER,
    source_folder TEXT,
    dest_folder TEXT,
    status TEXT DEFAULT 'scanned',
    scan_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DUPLICATE_SCANS_TABLE = """
CREATE TABLE IF NOT EXISTS duplicate_scans (
    id TEXT PRIMARY KEY,
    source_dir TEXT NOT NULL,
    against_dir TEXT,
    total_hash_groups INTEGER,
    total_hash_files INTEGER,
    total_meta_groups INTEGER,
    total_meta_files INTEGER,
    result_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre_normalized);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
CREATE INDEX IF NOT EXISTS idx_tracks_hash ON tracks(file_hash);
CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks(source_folder);
CREATE INDEX IF NOT EXISTS idx_tracks_dest ON tracks(dest_folder);
CREATE INDEX IF NOT EXISTS idx_duplicate_scans_created ON duplicate_scans(created_at DESC);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """Create database and tables if they don't exist."""
    path = db_path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(CREATE_TRACKS_TABLE)
        conn.executescript(CREATE_DUPLICATE_SCANS_TABLE)
        conn.executescript(CREATE_INDEXES)
    logger.info(f"Database initialized at {path}")


@contextmanager
def get_db(db_path: Optional[Path] = None):
    """Context manager for database connections."""
    path = db_path or DATABASE_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_tracks_batch(conn: sqlite3.Connection, tracks: List[Dict]) -> int:
    """Insert or update a batch of tracks. Returns number of rows affected."""
    if not tracks:
        return 0
    sql = """
    INSERT INTO tracks (
        file_path, file_name, file_extension, file_size, file_hash,
        genre_raw, genre_normalized, genres_parsed,
        artist, title, album, label, bpm, key, duration, year,
        source_folder, dest_folder, status, scan_error
    ) VALUES (
        :file_path, :file_name, :file_extension, :file_size, :file_hash,
        :genre_raw, :genre_normalized, :genres_parsed,
        :artist, :title, :album, :label, :bpm, :key, :duration, :year,
        :source_folder, :dest_folder, :status, :scan_error
    )
    ON CONFLICT(file_path) DO UPDATE SET
        file_name=excluded.file_name, file_extension=excluded.file_extension,
        file_size=excluded.file_size, file_hash=excluded.file_hash,
        genre_raw=excluded.genre_raw, genre_normalized=excluded.genre_normalized,
        genres_parsed=excluded.genres_parsed,
        artist=excluded.artist, title=excluded.title, album=excluded.album,
        label=excluded.label, bpm=excluded.bpm, key=excluded.key,
        duration=excluded.duration, year=excluded.year,
        source_folder=excluded.source_folder, dest_folder=excluded.dest_folder,
        status=excluded.status, scan_error=excluded.scan_error,
        updated_at=CURRENT_TIMESTAMP
    """
    conn.executemany(sql, tracks)
    return len(tracks)


def get_summary(conn: sqlite3.Connection) -> Dict:
    """Get collection summary statistics."""
    row = conn.execute("SELECT COUNT(*) as total FROM tracks").fetchone()
    total = row["total"] if row else 0

    row = conn.execute("SELECT COUNT(*) as c FROM tracks WHERE genre_raw IS NOT NULL AND genre_raw != ''").fetchone()
    with_genre = row["c"] if row else 0

    row = conn.execute("SELECT COUNT(*) as c FROM tracks WHERE genre_raw IS NULL OR genre_raw = ''").fetchone()
    without_genre = row["c"] if row else 0

    row = conn.execute("SELECT COALESCE(SUM(file_size), 0) as s FROM tracks").fetchone()
    total_size = row["s"] if row else 0

    row = conn.execute("SELECT COUNT(DISTINCT genre_normalized) as c FROM tracks WHERE genre_normalized IS NOT NULL").fetchone()
    unique_genres = row["c"] if row else 0

    row = conn.execute("SELECT COUNT(DISTINCT artist) as c FROM tracks WHERE artist IS NOT NULL AND artist != ''").fetchone()
    unique_artists = row["c"] if row else 0

    row = conn.execute("SELECT COUNT(DISTINCT label) as c FROM tracks WHERE label IS NOT NULL AND label != ''").fetchone()
    unique_labels = row["c"] if row else 0

    ext_rows = conn.execute("SELECT file_extension, COUNT(*) as c FROM tracks GROUP BY file_extension ORDER BY c DESC").fetchall()
    by_extension = {r["file_extension"]: r["c"] for r in ext_rows if r["file_extension"]}

    return {
        "total_tracks": total,
        "with_genre": with_genre,
        "without_genre": without_genre,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "unique_genres": unique_genres,
        "unique_artists": unique_artists,
        "unique_labels": unique_labels,
        "by_extension": by_extension,
    }


def get_genre_stats(conn: sqlite3.Connection) -> List[Dict]:
    """Get genre frequency statistics."""
    rows = conn.execute(
        "SELECT genre_normalized as genre, COUNT(*) as count FROM tracks "
        "WHERE genre_normalized IS NOT NULL AND genre_normalized != '' "
        "GROUP BY genre_normalized ORDER BY count DESC"
    ).fetchall()
    return [{"genre": r["genre"], "count": r["count"]} for r in rows]


def get_tracks_by_status(conn: sqlite3.Connection, status: str, limit: int = 500) -> List[Dict]:
    """Get tracks filtered by status."""
    rows = conn.execute(
        "SELECT * FROM tracks WHERE status = ? ORDER BY file_path LIMIT ?",
        (status, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def update_track_status(conn: sqlite3.Connection, file_path: str, status: str, dest_folder: Optional[str] = None) -> None:
    """Update a track's status and optionally its destination folder."""
    if dest_folder:
        conn.execute(
            "UPDATE tracks SET status=?, dest_folder=?, updated_at=CURRENT_TIMESTAMP WHERE file_path=?",
            (status, dest_folder, file_path),
        )
    else:
        conn.execute(
            "UPDATE tracks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE file_path=?",
            (status, file_path),
        )


def save_duplicate_scan(conn: sqlite3.Connection, scan_id: str, source_dir: str, against_dir: Optional[str], result: Dict) -> None:
    """Save a duplicate scan result to the database."""
    conn.execute(
        """INSERT INTO duplicate_scans (id, source_dir, against_dir, total_hash_groups, 
           total_hash_files, total_meta_groups, total_meta_files, result_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scan_id,
            source_dir,
            against_dir,
            result.get("total_hash_groups", 0),
            result.get("total_hash_files", 0),
            result.get("total_meta_groups", 0),
            result.get("total_meta_files", 0),
            json.dumps(result),
        ),
    )
    logger.info(f"Saved duplicate scan {scan_id} to database")


def get_duplicate_scan(conn: sqlite3.Connection, scan_id: str) -> Optional[Dict]:
    """Retrieve a duplicate scan result from the database."""
    row = conn.execute(
        "SELECT result_json FROM duplicate_scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if row:
        return json.loads(row["result_json"])
    return None


def list_duplicate_scans(conn: sqlite3.Connection, limit: int = 20) -> List[Dict]:
    """List recent duplicate scans."""
    rows = conn.execute(
        """SELECT id, source_dir, against_dir, total_hash_groups, total_hash_files,
           total_meta_groups, total_meta_files, created_at
           FROM duplicate_scans ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_duplicate_scan(conn: sqlite3.Connection, scan_id: str) -> bool:
    """Delete a duplicate scan from the database."""
    cursor = conn.execute("DELETE FROM duplicate_scans WHERE id = ?", (scan_id,))
    return cursor.rowcount > 0
