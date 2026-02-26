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
    logger.info("pyrekordbox imported successfully")
except ImportError as e:
    PYREKORDBOX_AVAILABLE = False
    logger.error(f"pyrekordbox import failed: {e}")
    logger.error("Install with: pip install pyrekordbox")
except Exception as e:
    PYREKORDBOX_AVAILABLE = False
    logger.error(f"Unexpected error importing pyrekordbox: {e}")


def get_rekordbox_db_path() -> Optional[Path]:
    """Get the default Rekordbox database path using pyrekordbox config."""
    if not PYREKORDBOX_AVAILABLE:
        return None
    
    try:
        # Use pyrekordbox config to find the database
        from pyrekordbox.config import get_config
        
        # Try Rekordbox 7 first
        try:
            rb7_config = get_config('REKORDBOX_7')
            if hasattr(rb7_config, 'db_path') and rb7_config.db_path:
                db_path = Path(rb7_config.db_path)
                if db_path.exists():
                    logger.info(f"Found Rekordbox 7 database at: {db_path}")
                    return db_path
        except Exception:
            pass
        
        # Try Rekordbox 6
        try:
            rb6_config = get_config('REKORDBOX_6')
            if hasattr(rb6_config, 'db_path') and rb6_config.db_path:
                db_path = Path(rb6_config.db_path)
                if db_path.exists():
                    logger.info(f"Found Rekordbox 6 database at: {db_path}")
                    return db_path
        except Exception:
            pass
        
        # Fallback to default locations
        if os.name == 'nt':  # Windows
            appdata = os.getenv('APPDATA')
            if appdata:
                rb_path = Path(appdata) / 'Pioneer' / 'rekordbox' / 'master.db'
                if rb_path.exists():
                    return rb_path
        else:  # macOS/Linux
            home = Path.home()
            rb_path = home / 'Library' / 'Pioneer' / 'rekordbox' / 'master.db'
            if rb_path.exists():
                return rb_path
        
    except Exception as e:
        logger.warning(f"Error getting Rekordbox config: {e}")
    
    return None


def get_available_databases() -> List[Dict]:
    """Find all available Rekordbox databases on the system."""
    databases = []
    
    if not PYREKORDBOX_AVAILABLE:
        return databases
    
    try:
        from pyrekordbox.config import get_config
        
        # Try Rekordbox 7
        try:
            rb7_config = get_config('REKORDBOX_7')
            if hasattr(rb7_config, 'db_path') and rb7_config.db_path:
                db_path = Path(rb7_config.db_path)
                if db_path.exists():
                    databases.append({
                        "path": str(db_path),
                        "name": "Rekordbox 7 (Default)",
                        "version": "7",
                        "is_default": True
                    })
        except Exception:
            pass
        
        # Try Rekordbox 6
        try:
            rb6_config = get_config('REKORDBOX_6')
            if hasattr(rb6_config, 'db_path') and rb6_config.db_path:
                db_path = Path(rb6_config.db_path)
                if db_path.exists():
                    databases.append({
                        "path": str(db_path),
                        "name": "Rekordbox 6",
                        "version": "6",
                        "is_default": len(databases) == 0
                    })
        except Exception:
            pass
        
        # Check common locations for additional databases
        if os.name == 'nt':  # Windows
            appdata = os.getenv('APPDATA')
            if appdata:
                pioneer_dir = Path(appdata) / 'Pioneer'
                if pioneer_dir.exists():
                    # Look for master.db files in subdirectories
                    for db_file in pioneer_dir.rglob('master.db'):
                        db_path_str = str(db_file)
                        # Avoid duplicates
                        if not any(db['path'] == db_path_str for db in databases):
                            databases.append({
                                "path": db_path_str,
                                "name": f"Rekordbox ({db_file.parent.name})",
                                "version": "unknown",
                                "is_default": False
                            })
        
    except Exception as e:
        logger.error(f"Error finding databases: {e}")
    
    return databases


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
        logger.info("=== Starting Rekordbox playlist tree retrieval ===")
        logger.info("Step 1: Creating Rekordbox6Database instance...")
        
        db = Rekordbox6Database()
        logger.info("Step 2: Database instance created successfully")
        
        db_path_used = get_rekordbox_db_path()
        db_path_str = str(db_path_used) if db_path_used else "Auto-detected"
        logger.info(f"Step 3: Database path: {db_path_str}")
        
        # Get all playlists
        playlists = []
        logger.info("Step 4: Getting playlist query...")
        playlist_query = db.get_playlist()
        logger.info("Step 5: Playlist query obtained, iterating...")
        
        count = 0
        max_items = 1000  # Increased limit for full collection
        
        for pl in playlist_query:
            if count >= max_items:
                logger.info(f"Reached max playlist limit of {max_items}")
                break
            
            try:
                playlist_id = pl.ID if hasattr(pl, 'ID') else None
                playlist_name = pl.Name if hasattr(pl, 'Name') and pl.Name else f"Playlist {playlist_id}"
                
                # Count tracks in playlist
                track_count = 0
                try:
                    if hasattr(pl, 'Tracks') and pl.Tracks:
                        track_count = len(list(pl.Tracks))
                except:
                    track_count = 0
                
                playlists.append({
                    "id": playlist_id,
                    "name": playlist_name,
                    "parent_id": pl.ParentID if hasattr(pl, 'ParentID') else None,
                    "is_folder": pl.Kind == 0 if hasattr(pl, 'Kind') else False,
                    "track_count": track_count
                })
                count += 1
            except Exception as item_error:
                logger.warning(f"Error processing playlist item: {item_error}")
                continue
        
        logger.info(f"Step 6: Processed {count} playlist items")
        
        # Build tree structure
        logger.info("Step 7: Building tree structure...")
        tree = build_tree(playlists)
        logger.info("Step 8: Tree structure built successfully")
        logger.info("=== Rekordbox playlist tree retrieval completed ===")
        
        return {
            "success": True,
            "db_path": db_path_str,
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
        
        logger.info(f"Reading tracks for playlist {playlist_id} (type: {type(playlist_id)})")
        
        # Open database
        db = Rekordbox6Database()
        
        # Get all playlists and find the one we want
        all_playlists = db.get_playlist()
        playlist = None
        found_ids = []
        
        for pl in all_playlists:
            if hasattr(pl, 'ID'):
                found_ids.append(pl.ID)
                # Try both int and string comparison
                if pl.ID == playlist_id or str(pl.ID) == str(playlist_id):
                    playlist = pl
                    logger.info(f"Found playlist with ID {pl.ID}")
                    break
        
        if not playlist:
            logger.error(f"Playlist {playlist_id} not found. First 10 available IDs: {found_ids[:10]}")
            return {
                "error": "Playlist not found",
                "message": f"Playlist with ID {playlist_id} not found. Available IDs: {len(found_ids)}"
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
        logger.info("=== Starting Rekordbox stats retrieval ===")
        logger.info("Step 1: Creating Rekordbox6Database instance...")
        
        db = Rekordbox6Database()
        logger.info("Step 2: Database instance created successfully")
        
        db_path_used = get_rekordbox_db_path()
        db_path_str = str(db_path_used) if db_path_used else "Auto-detected"
        logger.info(f"Step 3: Database path: {db_path_str}")
        
        # Try to get content count
        logger.info("Step 4: Getting content query...")
        content_query = db.get_content()
        logger.info("Step 5: Content query obtained, counting tracks...")
        
        total_tracks = 0
        for _ in content_query:
            total_tracks += 1
            if total_tracks >= 10000:  # Limit for performance
                logger.info(f"Reached limit of 10000 tracks")
                break
        
        logger.info(f"Step 6: Counted {total_tracks} tracks")
        
        # Try to get playlists
        logger.info("Step 7: Getting playlist query...")
        playlist_query = db.get_playlist()
        logger.info("Step 8: Playlist query obtained, counting...")
        
        total_playlists = 0
        total_folders = 0
        count = 0
        
        for p in playlist_query:
            if count >= 1000:  # Limit for performance
                break
            if hasattr(p, 'Kind'):
                if p.Kind == 0:
                    total_folders += 1
                else:
                    total_playlists += 1
            count += 1
        
        logger.info(f"Step 9: Counted {total_playlists} playlists and {total_folders} folders")
        logger.info("=== Rekordbox stats retrieval completed successfully ===")
        
        return {
            "success": True,
            "total_tracks": total_tracks,
            "total_playlists": total_playlists,
            "total_folders": total_folders,
            "db_path": db_path_str
        }
        
    except Exception as e:
        logger.exception(f"Error getting Rekordbox stats: {e}")
        return {
            "error": str(e),
            "message": "Failed to access Rekordbox database"
        }
