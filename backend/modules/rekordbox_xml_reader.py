"""
Rekordbox XML Parser
Reads and parses Rekordbox XML export files.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def parse_rekordbox_xml(xml_path: str) -> Dict:
    """
    Parse a Rekordbox XML export file.
    
    Args:
        xml_path: Path to the XML file
        
    Returns:
        Dict containing playlists and tracks
    """
    try:
        xml_file = Path(xml_path)
        logger.info(f"=== Starting XML parse for: {xml_path}")
        
        if not xml_file.exists():
            logger.error(f"File not found: {xml_path}")
            return {
                "error": "File not found",
                "message": f"XML file not found: {xml_path}"
            }
        
        file_size = xml_file.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"File size: {file_size:.2f} MB")
        
        logger.info("Parsing XML file...")
        # Parse XML
        tree = ET.parse(xml_file)
        root = tree.getroot()
        logger.info("XML parsed successfully")
        
        # Get DJ_PLAYLISTS node
        logger.info("Looking for PLAYLISTS node...")
        playlists_node = root.find('.//PLAYLISTS')
        if playlists_node is None:
            logger.error("No PLAYLISTS node found")
            return {
                "error": "Invalid XML",
                "message": "No PLAYLISTS node found in XML"
            }
        
        logger.info("Parsing playlist structure...")
        # Parse playlists recursively
        playlists = []
        parse_playlist_node(playlists_node, playlists, parent_id=None)
        
        logger.info(f"Parsed {len(playlists)} playlists from XML")
        
        # Build tree structure
        tree_structure = build_xml_tree(playlists)
        
        # Count stats
        total_playlists = len([p for p in playlists if p.get("type") == "0"])
        total_folders = len([p for p in playlists if p.get("type") == "1"])
        
        logger.info(f"Building tree structure with {len(tree_structure)} root items")
        logger.info(f"Stats - Playlists: {total_playlists}, Folders: {total_folders}")
        logger.info("=== XML parse completed successfully")
        
        return {
            "success": True,
            "source": "xml",
            "xml_path": str(xml_file),
            "tree": tree_structure,
            "total_playlists": total_playlists,
            "total_folders": total_folders
        }
        
    except ET.ParseError as e:
        logger.exception(f"XML parse error: {e}")
        return {
            "error": "XML parse error",
            "message": str(e)
        }
    except Exception as e:
        logger.exception(f"Error parsing Rekordbox XML: {e}")
        return {
            "error": "Parse error",
            "message": str(e)
        }


def parse_playlist_node(node, playlists: List[Dict], parent_id: Optional[str] = None, depth: int = 0):
    """Recursively parse playlist nodes."""
    # Safety check to prevent infinite recursion
    if depth > 50:
        logger.warning(f"Maximum recursion depth reached at depth {depth}")
        return
    
    for child in node:
        if child.tag == 'NODE':
            # Get attributes
            name = child.get('Name', '')
            node_type = child.get('Type', '0')  # 0 = playlist, 1 = folder
            key_id = child.get('KeyId', '')
            
            # Count only direct TRACK children, not all descendants
            track_count = len([t for t in child if t.tag == 'TRACK'])
            
            playlist_data = {
                "id": key_id,
                "name": name,
                "type": node_type,
                "is_folder": node_type == "1",
                "parent_id": parent_id,
                "track_count": track_count,
                "children": []
            }
            
            playlists.append(playlist_data)
            
            # Recursively parse children (only NODE children, not TRACK children)
            parse_playlist_node(child, playlists, parent_id=key_id, depth=depth + 1)


def build_xml_tree(playlists: List[Dict]) -> List[Dict]:
    """Build hierarchical tree from flat playlist list."""
    # Create lookup dict
    items_by_id = {}
    for item in playlists:
        items_by_id[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "parent_id": item.get("parent_id"),
            "is_folder": item["is_folder"],
            "track_count": item["track_count"],
            "children": []
        }
    
    # Build tree
    root_items = []
    for item in playlists:
        parent_id = item.get("parent_id")
        if parent_id is None:
            root_items.append(items_by_id[item["id"]])
        elif parent_id in items_by_id:
            items_by_id[parent_id]["children"].append(items_by_id[item["id"]])
    
    # Sort function: folders first, then playlists, both alphabetically
    def sort_key(item):
        return (0 if item.get("is_folder") else 1, item.get("name", "").lower())
    
    def sort_tree(items):
        items.sort(key=sort_key)
        for item in items:
            if item.get("children"):
                sort_tree(item["children"])
    
    sort_tree(root_items)
    
    return root_items


def get_xml_playlist_tracks(xml_path: str, playlist_id: str) -> Dict:
    """Get tracks from a specific playlist in XML."""
    try:
        xml_file = Path(xml_path)
        if not xml_file.exists():
            return {
                "error": "File not found",
                "message": f"XML file not found: {xml_path}"
            }
        
        # Parse XML
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Find the playlist node
        playlist_node = root.find(f'.//NODE[@KeyId="{playlist_id}"]')
        if playlist_node is None:
            return {
                "error": "Playlist not found",
                "message": f"Playlist {playlist_id} not found in XML"
            }
        
        # Get tracks
        track_nodes = playlist_node.findall('.//TRACK')
        tracks = []
        
        for track_node in track_nodes:
            track_key = track_node.get('Key', '')
            
            # Find track details in COLLECTION
            track_detail = root.find(f'.//COLLECTION/TRACK[@TrackID="{track_key}"]')
            if track_detail is not None:
                # Decode file location
                location = track_detail.get('Location', '')
                if location.startswith('file://localhost/'):
                    location = unquote(location.replace('file://localhost/', ''))
                
                tracks.append({
                    "id": track_key,
                    "title": track_detail.get('Name', 'Unknown'),
                    "artist": track_detail.get('Artist', 'Unknown'),
                    "album": track_detail.get('Album', ''),
                    "genre": track_detail.get('Genre', ''),
                    "bpm": track_detail.get('AverageBpm', ''),
                    "duration": track_detail.get('TotalTime', ''),
                    "year": track_detail.get('Year', ''),
                    "location": location,
                    "rating": track_detail.get('Rating', '0'),
                    "key": track_detail.get('Tonality', ''),
                    "comments": track_detail.get('Comments', '')
                })
        
        return {
            "success": True,
            "tracks": tracks,
            "track_count": len(tracks)
        }
        
    except Exception as e:
        logger.exception(f"Error getting XML playlist tracks: {e}")
        return {
            "error": "Error reading tracks",
            "message": str(e),
            "tracks": []
        }
