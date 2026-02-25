"""Rekordbox database reader using pyrekordbox."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
import os

logger = logging.getLogger(__name__)

# Try to import pyrekordbox
try:
    from pyrekordbox import Rekordbox6Database
    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    logger.warning("pyrekordbox not available. Install with: pip install pyrekordbox")


def get_rekordbox_db_path() -> Optional[Path]:
    """Get the default Rekordbox database path based on OS."""
    if os.name == 'nt':  # Windows
        # Default path for Rekordbox 6/7 on Windows
        appdata = os.getenv('APPDATA')
        if appdata:
            rb_path = Path(appdata) / 'Pioneer' / 'rekordbox' / 'master.db'
            if rb_path.exists():
                return rb_path
            # Try alternative path
            rb_path = Path(appdata) / 'Pioneer' / 'rekordbox' / 'datafile.edb'
            if rb_path.exists():
                return rb_path
    else:  # macOS/Linux
        home = Path.home()
        rb_path = home / 'Library' / 'Pioneer' / 'rekordbox' / 'master.db'
        if rb_path.exists():
            return rb_path
    
    return None


def get_playlist_tree(db_path: Optional[str] = None) -> Dict:
    """
    Get the complete playlist folder structure from Rekordbox.
    
    Returns a tree structure with folders and playlists.
    """
    if not PYREKORDBOX_AVAILABLE:
        return {
            "error": "pyrekordbox not installed",
            "message": "Install with: pip install pyrekordbox"
        }
    
    try:
        # Use provided path or find default
        if db_path:
            db_file = Path(db_path)
        else:
            db_file = get_rekordbox_db_path()
        
        if not db_file or not db_file.exists():
            return {
                "error": "Database not found",
                "message": f"Rekordbox database not found at: {db_file}",
                "searched_path": str(db_file) if db_file else "No default path"
            }
        
        logger.info(f"Reading Rekordbox database from: {db_file}")
        
        # Open database
        db = Rekordbox6Database(str(db_file))
        
        # Get all playlists
        playlists = []
        try:
            # Query playlists from database
            # Note: This is a simplified version - actual implementation depends on pyrekordbox API
            playlist_query = db.get_playlist()
            
            for pl in playlist_query:
                playlists.append({
                    "id": pl.ID if hasattr(pl, 'ID') else None,
                    "name": pl.Name if hasattr(pl, 'Name') else "Unknown",
                    "parent_id": pl.ParentID if hasattr(pl, 'ParentID') else None,
                    "is_folder": pl.Kind == 0 if hasattr(pl, 'Kind') else False,
                    "track_count": len(pl.Tracks) if hasattr(pl, 'Tracks') else 0
                })
        except Exception as e:
            logger.error(f"Error reading playlists: {e}")
            playlists = []
        
        # Build tree structure
        tree = build_tree(playlists)
        
        return {
            "success": True,
            "db_path": str(db_file),
            "tree": tree,
            "total_playlists": len([p for p in playlists if not p["is_folder"]]),
            "total_folders": len([p for p in playlists if p["is_folder"]])
        }
        
    except Exception as e:
        logger.exception(f"Error reading Rekordbox database: {e}")
        return {
            "error": "Database read error",
            "message": str(e)
        }


def build_tree(playlists: List[Dict]) -> List[Dict]:
    """Build hierarchical tree from flat playlist list."""
    # Create lookup dict
    items_by_id = {item["id"]: {**item, "children": []} for item in playlists}
    
    # Build tree
    root_items = []
    for item in playlists:
        parent_id = item.get("parent_id")
        if parent_id is None or parent_id == 0:
            root_items.append(items_by_id[item["id"]])
        elif parent_id in items_by_id:
            items_by_id[parent_id]["children"].append(items_by_id[item["id"]])
    
    return root_items


def get_playlist_tracks(playlist_id: int, db_path: Optional[str] = None) -> Dict:
    """Get all tracks in a specific playlist."""
    if not PYREKORDBOX_AVAILABLE:
        return {
            "error": "pyrekordbox not installed",
            "message": "Install with: pip install pyrekordbox"
        }
    
    try:
        # Use provided path or find default
        if db_path:
            db_file = Path(db_path)
        else:
            db_file = get_rekordbox_db_path()
        
        if not db_file or not db_file.exists():
            return {
                "error": "Database not found",
                "message": f"Rekordbox database not found"
            }
        
        logger.info(f"Reading tracks for playlist {playlist_id}")
        
        # Open database
        db = Rekordbox6Database(str(db_file))
        
        # Get playlist
        playlist = db.get_playlist(playlist_id)
        
        if not playlist:
            return {
                "error": "Playlist not found",
                "message": f"Playlist with ID {playlist_id} not found"
            }
        
        # Get tracks
        tracks = []
        if hasattr(playlist, 'Tracks'):
            for track in playlist.Tracks:
                tracks.append({
                    "id": track.ID if hasattr(track, 'ID') else None,
                    "title": track.Title if hasattr(track, 'Title') else "Unknown",
                    "artist": track.Artist if hasattr(track, 'Artist') else "Unknown",
                    "album": track.Album if hasattr(track, 'Album') else "",
                    "genre": track.Genre if hasattr(track, 'Genre') else "",
                    "bpm": track.BPM if hasattr(track, 'BPM') else None,
                    "key": track.Key if hasattr(track, 'Key') else "",
                    "duration": track.Duration if hasattr(track, 'Duration') else None,
                    "file_path": track.FilePath if hasattr(track, 'FilePath') else ""
                })
        
        return {
            "success": True,
            "playlist_id": playlist_id,
            "playlist_name": playlist.Name if hasattr(playlist, 'Name') else "Unknown",
            "tracks": tracks,
            "track_count": len(tracks)
        }
        
    except Exception as e:
        logger.exception(f"Error reading playlist tracks: {e}")
        return {
            "error": "Error reading tracks",
            "message": str(e)
        }


def get_rekordbox_stats(db_path: Optional[str] = None) -> Dict:
    """Get statistics about the Rekordbox library."""
    if not PYREKORDBOX_AVAILABLE:
        return {
            "error": "pyrekordbox not installed"
        }
    
    try:
        if db_path:
            db_file = Path(db_path)
        else:
            db_file = get_rekordbox_db_path()
        
        if not db_file or not db_file.exists():
            return {
                "error": "Database not found"
            }
        
        db = Rekordbox6Database(str(db_file))
        
        # Get counts
        total_tracks = len(db.get_content())
        playlists = db.get_playlist()
        total_playlists = len([p for p in playlists if p.Kind != 0])
        total_folders = len([p for p in playlists if p.Kind == 0])
        
        return {
            "success": True,
            "total_tracks": total_tracks,
            "total_playlists": total_playlists,
            "total_folders": total_folders,
            "db_path": str(db_file)
        }
        
    except Exception as e:
        logger.exception(f"Error getting Rekordbox stats: {e}")
        return {
            "error": str(e)
        }
