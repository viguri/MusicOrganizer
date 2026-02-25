"""API routes for Rekordbox database browsing."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.modules.rekordbox_reader import (
    get_playlist_tree,
    get_playlist_tracks,
    get_rekordbox_stats,
    get_rekordbox_db_path,
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
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result)
        
        return result
    except Exception as e:
        logger.exception(f"Error getting playlist tree: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/playlist/{playlist_id}/tracks")
async def api_get_playlist_tracks(
    playlist_id: int,
    db_path: Optional[str] = Query(None)
):
    """Get all tracks in a specific playlist."""
    try:
        result = get_playlist_tracks(playlist_id, db_path)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result)
        
        return result
    except Exception as e:
        logger.exception(f"Error getting playlist tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def api_get_rekordbox_stats(db_path: Optional[str] = Query(None)):
    """Get statistics about the Rekordbox library."""
    try:
        result = get_rekordbox_stats(db_path)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result)
        
        return result
    except Exception as e:
        logger.exception(f"Error getting Rekordbox stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
