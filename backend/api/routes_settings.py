"""API routes for settings: config, folder_mapping, label_mapping."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import (
    FOLDER_MAPPING_PATH,
    LABEL_MAPPING_PATH,
    DEFAULT_MASTER_COLLECTION,
    DEFAULT_STYLES_DIR,
    DEFAULT_NEW_RELEASES_DIR,
    TARGET_FOLDER_COUNT,
)
from backend.modules.genre_analyzer import load_folder_mapping, load_label_mapping
from backend.modules.genre_mapper import reload_mappings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


class UpdateFolderMappingRequest(BaseModel):
    mapping: Dict[str, List[str]]


class UpdateLabelMappingRequest(BaseModel):
    mapping: Dict[str, str]


@router.get("/config")
async def get_config():
    """Get current configuration."""
    return {
        "styles_dir": DEFAULT_STYLES_DIR,
        "new_releases_dir": DEFAULT_NEW_RELEASES_DIR,
        "master_collection": DEFAULT_MASTER_COLLECTION,
        "target_folder_count": TARGET_FOLDER_COUNT,
    }


@router.get("/folder-mapping")
async def get_folder_mapping():
    """Get current folder mapping."""
    return load_folder_mapping()


@router.put("/folder-mapping")
async def update_folder_mapping(request: UpdateFolderMappingRequest):
    """Update folder mapping JSON."""
    try:
        FOLDER_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FOLDER_MAPPING_PATH, "w", encoding="utf-8") as f:
            json.dump(request.mapping, f, indent=2, ensure_ascii=False)
        reload_mappings()
        return {"status": "ok", "folders": len(request.mapping)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/label-mapping")
async def get_label_mapping():
    """Get current label mapping."""
    return load_label_mapping()


@router.put("/label-mapping")
async def update_label_mapping(request: UpdateLabelMappingRequest):
    """Update label mapping JSON."""
    try:
        LABEL_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LABEL_MAPPING_PATH, "w", encoding="utf-8") as f:
            json.dump(request.mapping, f, indent=2, ensure_ascii=False)
        reload_mappings()
        return {"status": "ok", "labels": len(request.mapping)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
