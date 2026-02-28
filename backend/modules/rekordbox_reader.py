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
        
        for pl in playlist_query:
            
            try:
                # Keep ID as string for consistent comparison
                playlist_id = str(pl.ID) if hasattr(pl, 'ID') else None
                
                # Get playlist name - handle None values
                playlist_name = None
                has_real_name = False
                if hasattr(pl, 'Name') and pl.Name:
                    playlist_name = str(pl.Name).strip()
                    has_real_name = True
                
                # Determine if it's a folder using the is_folder attribute
                is_folder = False
                if hasattr(pl, 'is_folder'):
                    is_folder = pl.is_folder
                elif hasattr(pl, 'Kind'):
                    is_folder = pl.Kind == 0
                
                # Count tracks in playlist
                track_count = 0
                try:
                    if hasattr(pl, 'Songs') and pl.Songs:
                        track_count = len(list(pl.Songs))
                except:
                    track_count = 0
                
                # Skip playlists without name and without tracks (unless it's a folder)
                if not has_real_name and not is_folder and track_count == 0:
                    continue
                
                # If no name, use ID as fallback (only for items we're keeping)
                if not playlist_name:
                    playlist_name = f"Playlist {playlist_id}"
                
                # Get parent ID - keep as string for consistent comparison
                parent_id = None
                if hasattr(pl, 'ParentID'):
                    if pl.ParentID and pl.ParentID != 'root':
                        parent_id = str(pl.ParentID)
                
                playlists.append({
                    "id": playlist_id,
                    "name": playlist_name,
                    "parent_id": parent_id,
                    "is_folder": is_folder,
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
    
    # Sort function: folders first, then playlists, both alphabetically by name
    def sort_key(item):
        # Folders (is_folder=True) come first (0), playlists second (1)
        # Then sort alphabetically by name (case-insensitive)
        return (0 if item.get("is_folder") else 1, item.get("name", "").lower())
    
    # Recursively sort all levels
    def sort_tree(items):
        items.sort(key=sort_key)
        for item in items:
            if item.get("children"):
                sort_tree(item["children"])
    
    sort_tree(root_items)
    
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
        
        # Get tracks using Songs (not Tracks)
        tracks = []
        if hasattr(playlist, 'Songs') and playlist.Songs:
            for song in playlist.Songs:
                if hasattr(song, 'Content') and song.Content:
                    content = song.Content
                    
                    artist_name = "Unknown"
                    if hasattr(content, 'Artist') and content.Artist:
                        artist_name = content.Artist.Name if hasattr(content.Artist, 'Name') else "Unknown"
                    
                    album_name = ""
                    if hasattr(content, 'Album') and content.Album:
                        album_name = content.Album.Name if hasattr(content.Album, 'Name') else ""
                    
                    genre_name = ""
                    if hasattr(content, 'Genre') and content.Genre:
                        genre_name = content.Genre.Name if hasattr(content.Genre, 'Name') else ""
                    
                    # Determine track location
                    file_path = content.FolderPath if hasattr(content, 'FolderPath') else ""
                    location_status = "unknown"
                    file_exists = False
                    
                    if file_path:
                        file_path_lower = file_path.lower()
                        
                        # Check if it's a cloud path
                        is_cloud = any(keyword in file_path_lower for keyword in ['dropbox', 'icloud', 'onedrive', 'google drive', 'cloud'])
                        
                        # Check if file exists physically
                        try:
                            from pathlib import Path
                            file_exists = Path(file_path).exists()
                        except:
                            file_exists = False
                        
                        # Determine location status
                        if is_cloud and file_exists:
                            location_status = "both"  # Synced to local from cloud
                        elif is_cloud:
                            location_status = "cloud"  # Only in cloud
                        elif file_exists:
                            location_status = "local"  # Only local
                        else:
                            location_status = "missing"  # File not found
                    
                    tracks.append({
                        "id": content.ID if hasattr(content, 'ID') else None,
                        "title": content.Title if hasattr(content, 'Title') else "Unknown",
                        "artist": artist_name,
                        "album": album_name,
                        "genre": genre_name,
                        "bpm": content.BPM if hasattr(content, 'BPM') else None,
                        "key": content.Key if hasattr(content, 'Key') else "",
                        "duration": content.Duration if hasattr(content, 'Duration') else None,
                        "file_path": file_path,
                        "track_no": song.TrackNo if hasattr(song, 'TrackNo') else None,
                        "location_status": location_status,
                        "file_exists": file_exists
                    })
        
        return {
            "success": True,
            "playlist_id": playlist_id,
            "playlist_name": playlist.Name if hasattr(playlist, 'Name') else f"Playlist {playlist_id}",
            "tracks": tracks,
            "track_count": len(tracks)
        }
        
    except Exception as e:
        logger.exception(f"Error reading playlist tracks: {e}")
        return {
            "error": "Error reading tracks",
            "message": str(e)
        }


def get_rekordbox_stats(db_path: Optional[str] = None, limit_tracks: bool = True) -> Dict:
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
            if limit_tracks and total_tracks >= 10000:
                logger.info(f"Reached limit of 10000 tracks")
                break
        
        logger.info(f"Step 6: Counted {total_tracks} tracks")
        
        # Try to get playlists
        logger.info("Step 7: Getting playlist query...")
        playlist_query = db.get_playlist()
        logger.info("Step 8: Playlist query obtained, counting...")
        
        total_playlists = 0
        total_folders = 0
        
        for p in playlist_query:
            is_folder = False
            if hasattr(p, 'is_folder'):
                is_folder = p.is_folder
            elif hasattr(p, 'Kind'):
                is_folder = p.Kind == 0
            
            if is_folder:
                total_folders += 1
            else:
                total_playlists += 1
        
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
