"""API routes for scanning directories and analyzing genres."""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.api.websocket import manager
from backend.modules.scanner import discover_audio_files, scan_directory
from backend.modules.genre_parser import parse_genre
from backend.modules.genre_analyzer import analyze_genres, load_folder_mapping, load_label_mapping
from backend.modules.database import init_db, get_db, upsert_tracks_batch, get_summary, get_genre_stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scan", tags=["scan"])

# In-memory task tracking
_tasks: Dict[str, Dict] = {}


class ScanRequest(BaseModel):
    directory: str
    save_to_db: bool = True
    recursive: bool = True


class AnalyzeRequest(BaseModel):
    directory: str
    use_embeddings: bool = True
    target_folders: int = 50
    recursive: bool = True


@router.post("/start")
async def start_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """Start scanning a directory for audio files."""
    directory = request.directory
    if not Path(directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "running", "type": "scan"}

    background_tasks.add_task(_run_scan, task_id, directory, request.save_to_db, request.recursive)

    return {"task_id": task_id, "status": "started", "directory": directory}


@router.post("/analyze-genres")
async def start_analyze_genres(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Analyze genre distribution and propose folder structure."""
    directory = request.directory
    if not Path(directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "running", "type": "analyze"}

    background_tasks.add_task(_run_analyze, task_id, directory, request.use_embeddings, request.target_folders, request.recursive)

    return {"task_id": task_id, "status": "started"}


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a scan/analyze task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/summary")
async def get_collection_summary():
    """Get collection summary from database."""
    try:
        with get_db() as conn:
            return get_summary(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/genre-stats")
async def get_genre_statistics():
    """Get genre frequency statistics."""
    try:
        with get_db() as conn:
            return get_genre_stats(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder-mapping")
async def get_folder_mapping():
    """Get current folder mapping."""
    return load_folder_mapping()


@router.get("/label-mapping")
async def get_label_mapping():
    """Get current label mapping."""
    return load_label_mapping()


# ── Background tasks ──────────────────────────────────────────────────────────

async def _run_scan(task_id: str, directory: str, save_to_db: bool, recursive: bool = True):
    """Background task for scanning."""
    loop = asyncio.get_event_loop()

    mode = "recursive" if recursive else "top-level only"
    await manager.send_status(task_id, "started", f"Scanning {directory} ({mode})...")

    try:
        file_paths = await loop.run_in_executor(None, lambda: discover_audio_files(directory, recursive=recursive))
        total = len(file_paths)
        await manager.send_progress(task_id, 0, total, f"Found {total} audio files")

        def progress_cb(current, total_count):
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, current, total_count, f"Scanning: {current}/{total_count}"),
                loop,
            )

        tracks = await loop.run_in_executor(
            None, lambda: scan_directory(directory, progress_callback=progress_cb, recursive=recursive)
        )

        if save_to_db:
            await manager.send_status(task_id, "saving", "Saving to database...")
            init_db()
            with get_db() as conn:
                batch = []
                for track in tracks:
                    genres = parse_genre(track.genre_raw)
                    primary_genre = genres[0] if genres else None
                    source_folder = Path(track.file_path).parent.name

                    batch.append({
                        "file_path": track.file_path,
                        "file_name": track.file_name,
                        "file_extension": track.file_extension,
                        "file_size": track.file_size,
                        "file_hash": None,
                        "genre_raw": track.genre_raw,
                        "genre_normalized": primary_genre,
                        "genres_parsed": ",".join(genres) if genres else None,
                        "artist": track.artist,
                        "title": track.title,
                        "album": track.album,
                        "label": track.label,
                        "bpm": track.bpm,
                        "key": track.key,
                        "duration": track.duration,
                        "year": track.year,
                        "source_folder": source_folder,
                        "dest_folder": None,
                        "status": "scanned",
                        "scan_error": track.error,
                    })

                    if len(batch) >= 500:
                        upsert_tracks_batch(conn, batch)
                        batch = []

                if batch:
                    upsert_tracks_batch(conn, batch)

        with_genre = sum(1 for t in tracks if t.genre_raw)
        without_genre = sum(1 for t in tracks if not t.genre_raw)
        errors = sum(1 for t in tracks if t.error)

        result = {
            "total_files": len(tracks),
            "with_genre": with_genre,
            "without_genre": without_genre,
            "errors": errors,
            "directory": directory,
        }

        _tasks[task_id] = {"status": "completed", "type": "scan", "result": result}
        await manager.send_result(task_id, result)
        await manager.send_status(task_id, "completed", f"Scan complete: {len(tracks)} files")

    except Exception as e:
        logger.exception(f"Scan failed: {e}")
        _tasks[task_id] = {"status": "error", "type": "scan", "error": str(e)}
        await manager.send_status(task_id, "error", str(e))


async def _run_analyze(task_id: str, directory: str, use_embeddings: bool, target_folders: int, recursive: bool = True):
    """Background task for genre analysis."""
    loop = asyncio.get_event_loop()

    mode = "recursive" if recursive else "top-level only"
    await manager.send_status(task_id, "started", f"Analyzing genres in {directory} ({mode})...")

    try:
        def progress_cb(current, total_count):
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, current, total_count, f"Analyzing: {current}/{total_count}"),
                loop,
            )

        result = await loop.run_in_executor(
            None,
            lambda: analyze_genres(directory, use_embeddings=use_embeddings, target_folders=target_folders, progress_callback=progress_cb, recursive=recursive),
        )

        _tasks[task_id] = {"status": "completed", "type": "analyze", "result": result}
        await manager.send_result(task_id, result)
        await manager.send_status(task_id, "completed", "Genre analysis complete")

    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        _tasks[task_id] = {"status": "error", "type": "analyze", "error": str(e)}
        await manager.send_status(task_id, "error", str(e))
