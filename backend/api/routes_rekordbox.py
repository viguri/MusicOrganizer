"""API routes for Rekordbox database browsing."""

import logging
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.modules.rekordbox_reader import (
    get_rekordbox_db_path,
    get_playlist_tree,
    get_playlist_tracks,
    get_rekordbox_stats,
    get_available_databases
)
from backend.modules.rekordbox_xml_reader import (
    parse_rekordbox_xml,
    get_xml_playlist_tracks
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rekordbox", tags=["rekordbox"])


class RekordboxPathRequest(BaseModel):
    db_path: Optional[str] = None


@router.get("/tree")
async def api_get_playlist_tree(db_path: Optional[str] = Query(None)):
    """Get the complete Rekordbox playlist folder structure."""
    try:
        result = get_playlist_tree(db_path)
        return result
    except Exception as e:
        logger.exception(f"Error getting playlist tree: {e}")
        return {
            "error": "Internal error",
            "message": str(e)
        }


@router.get("/playlist/{playlist_id}/tracks")
async def api_get_playlist_tracks(
    playlist_id: int,
    db_path: Optional[str] = Query(None)
):
    """Get all tracks in a specific playlist."""
    try:
        result = get_playlist_tracks(playlist_id, db_path)
        return result
    except Exception as e:
        logger.exception(f"Error getting playlist tracks: {e}")
        return {
            "error": "Internal error",
            "message": str(e)
        }


@router.get("/stats")
async def api_get_rekordbox_stats(
    db_path: Optional[str] = Query(None),
    limit_tracks: bool = Query(False, description="Limit track count to 10,000 for performance")
):
    """Get statistics about the Rekordbox library."""
    try:
        result = get_rekordbox_stats(db_path, limit_tracks)
        return result
    except Exception as e:
        logger.exception(f"Error getting Rekordbox stats: {e}")
        return {
            "error": "Internal error",
            "message": str(e)
        }


@router.get("/db-path")
async def api_get_db_path():
    """Get the default Rekordbox database path."""
    try:
        db_path = get_rekordbox_db_path()
        
        if db_path:
            return {
                "success": True,
                "db_path": str(db_path),
                "exists": db_path.exists()
            }
        else:
            return {
                "success": False,
                "message": "Rekordbox database not found in default locations"
            }
    except Exception as e:
        logger.exception(f"Error getting DB path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases")
async def api_get_available_databases():
    """Get list of available Rekordbox databases."""
    try:
        databases = get_available_databases()
        return {
            "success": True,
            "databases": databases,
            "count": len(databases)
        }
    except Exception as e:
        logger.exception(f"Error getting available databases: {e}")
        return {
            "success": False,
            "error": str(e),
            "databases": []
        }


@router.get("/xml/parse")
async def api_parse_xml(xml_path: str = Query(..., description="Path to Rekordbox XML file")):
    """Parse a Rekordbox XML export file."""
    try:
        result = parse_rekordbox_xml(xml_path)
        return result
    except Exception as e:
        logger.exception(f"Error parsing XML: {e}")
        return {
            "error": "Internal error",
            "message": str(e)
        }


@router.get("/xml/playlist/{playlist_id}/tracks")
async def api_get_xml_playlist_tracks(
    playlist_id: str,
    xml_path: str = Query(..., description="Path to Rekordbox XML file")
):
    """Get tracks from a specific playlist in XML."""
    try:
        result = get_xml_playlist_tracks(xml_path, playlist_id)
        return result
    except Exception as e:
        logger.exception(f"Error getting XML playlist tracks: {e}")
        return {
            "error": "Internal error",
            "message": str(e)
        }


@router.get("/stream")
async def stream_audio_file(file_path: str = Query(..., description="Absolute path to the audio file")):
    """Stream an audio file for playback."""
    try:
        audio_file = Path(file_path)
        
        if not audio_file.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        if not audio_file.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        
        # Check if it's an audio file by extension
        audio_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma', '.aiff', '.alac'}
        if audio_file.suffix.lower() not in audio_extensions:
            raise HTTPException(status_code=400, detail="Not a supported audio file")
        
        return FileResponse(
            path=str(audio_file),
            media_type='audio/mpeg',
            filename=audio_file.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error streaming audio file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
