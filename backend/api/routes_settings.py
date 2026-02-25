"""API routes for settings: config, folder_mapping, label_mapping, filesystem browsing."""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
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


def _list_windows_drives() -> List[Dict[str, str]]:
    """List logical drives on Windows without probing each letter path.

    Using GetLogicalDrives avoids slow/hanging checks on unavailable network drives.
    """
    try:
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        drives: List[Dict[str, str]] = []
        for i in range(26):
            if mask & (1 << i):
                letter = chr(ord("A") + i)
                drives.append({"name": f"{letter}:", "path": f"{letter}:\\"})
        return drives
    except Exception:
        # Conservative fallback if WinAPI call is unavailable
        drives: List[Dict[str, str]] = []
        for i in range(26):
            letter = chr(ord("A") + i)
            drive = Path(f"{letter}:\\")
            if drive.exists():
                drives.append({"name": f"{letter}:", "path": str(drive)})
        return drives


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


@router.get("/browse")
async def browse_directory(path: str = Query("", description="Directory path to browse. Empty returns drives/root.")):
    """Browse filesystem directories for the folder picker dialog.

    Returns the current path, parent path, and list of subdirectories.
    When path is empty, returns available drives (Windows) or root (Unix).
    """
    # If no path provided, return drives (Windows) or root (Unix)
    if not path or path.strip() == "":
        if sys.platform == "win32":
            drives = _list_windows_drives()
            return {"current": "", "parent": "", "directories": drives}
        else:
            path = "/"

    p = Path(path)
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    # List subdirectories (skip hidden and system folders)
    dirs = []
    try:
        for entry in sorted(p.iterdir()):
            if entry.is_dir():
                name = entry.name
                if name.startswith(".") or name == "$RECYCLE.BIN" or name == "System Volume Information":
                    continue
                dirs.append({"name": name, "path": str(entry)})
    except PermissionError:
        pass

    parent = str(p.parent) if p.parent != p else ""

    return {
        "current": str(p),
        "parent": parent,
        "directories": dirs,
    }
