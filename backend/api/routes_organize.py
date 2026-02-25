"""API routes for organizing, cleaning names, and detecting duplicates."""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.api.websocket import manager
from backend.modules.organizer import (
    plan_organize,
    execute_plan,
    apply_folder_overrides,
    rollback,
    create_folder_structure,
    cleanup_empty_folders,
    OrganizePlan,
)
from backend.modules.name_cleaner import clean_directory
from backend.modules.duplicates import find_duplicates, delete_duplicates, move_duplicates
from backend.modules.database import (
    get_db,
    save_duplicate_scan,
    get_duplicate_scan,
    list_duplicate_scans,
    delete_duplicate_scan,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/organize", tags=["organize"])

# In-memory task and plan tracking
_tasks: Dict[str, Dict] = {}
_plans: Dict[str, OrganizePlan] = {}
_duplicate_results: Dict[str, Dict] = {}


class OrganizeRequest(BaseModel):
    source: str
    dest: str
    dry_run: bool = True
    recursive: bool = True


class CleanNamesRequest(BaseModel):
    directory: str
    dry_run: bool = True


class DuplicatesRequest(BaseModel):
    source: str
    against: str | None = None


class DeleteDuplicatesRequest(BaseModel):
    use_hash: bool = True
    use_metadata: bool = False
    dry_run: bool = True


class MoveDuplicatesRequest(BaseModel):
    destination_folder: str
    use_hash: bool = True
    use_metadata: bool = False
    dry_run: bool = True
    preserve_structure: bool = True


class RollbackRequest(BaseModel):
    rollback_log: str


class PlanFolderOverridesRequest(BaseModel):
    overrides: Dict[str, str]


@router.post("/plan")
async def api_plan_organize(request: OrganizeRequest, background_tasks: BackgroundTasks):
    """Plan file organization (dry-run). Returns what would be moved."""
    if not Path(request.source).is_dir():
        raise HTTPException(status_code=400, detail=f"Source not found: {request.source}")
    if not Path(request.dest).is_dir():
        raise HTTPException(status_code=400, detail=f"Destination not found: {request.dest}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "running", "type": "plan"}

    background_tasks.add_task(_run_plan, task_id, request.source, request.dest, request.recursive)
    return {"task_id": task_id, "status": "started"}


@router.post("/execute/{plan_id}")
async def api_execute_plan(plan_id: str, background_tasks: BackgroundTasks):
    """Execute a previously planned organize operation."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found. Create a plan first with /plan")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "running", "type": "execute"}

    background_tasks.add_task(_run_execute, task_id, plan)
    return {"task_id": task_id, "status": "started", "files_to_move": plan.files_to_move}


@router.post("/plan/{plan_id}/folders")
async def api_update_plan_folders(plan_id: str, request: PlanFolderOverridesRequest):
    """Apply per-folder overrides to an existing plan before execution."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found. Create a plan first with /plan")

    updated_plan = apply_folder_overrides(plan, request.overrides)
    _plans[plan_id] = updated_plan
    return {"status": "updated", "result": updated_plan.to_dict()}


@router.post("/rollback")
async def api_rollback(request: RollbackRequest):
    """Rollback a previous organize operation."""
    try:
        result = rollback(request.rollback_log)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clean-names")
async def api_clean_names(request: CleanNamesRequest, background_tasks: BackgroundTasks):
    """Clean audio file names in a directory."""
    if not Path(request.directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {request.directory}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "running", "type": "clean-names"}

    background_tasks.add_task(_run_clean_names, task_id, request.directory, request.dry_run)
    return {"task_id": task_id, "status": "started"}


@router.post("/duplicates")
async def api_scan_duplicates(request: DuplicatesRequest, background_tasks: BackgroundTasks):
    """Scan for duplicate files."""
    if not Path(request.source).is_dir():
        raise HTTPException(status_code=400, detail=f"Source not found: {request.source}")
    if request.against and not Path(request.against).is_dir():
        raise HTTPException(status_code=400, detail=f"Against directory not found: {request.against}")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "running", "type": "duplicates"}

    background_tasks.add_task(_run_duplicates, task_id, request.source, request.against)
    return {"task_id": task_id, "status": "started"}


@router.post("/duplicates/{task_id}/delete")
async def api_delete_duplicates(task_id: str, request: DeleteDuplicatesRequest):
    """Delete duplicate files from a previous scan result."""
    # Try memory first, then database
    duplicate_result = _duplicate_results.get(task_id)
    if not duplicate_result:
        with get_db() as conn:
            duplicate_result = get_duplicate_scan(conn, task_id)
    
    if not duplicate_result:
        raise HTTPException(
            status_code=404, 
            detail="Duplicate scan result not found. Run /duplicates first or scan may have expired."
        )
    
    try:
        result = delete_duplicates(
            duplicate_result,
            use_hash=request.use_hash,
            use_metadata=request.use_metadata,
            dry_run=request.dry_run
        )
        return result
    except Exception as e:
        logger.exception(f"Delete duplicates failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/duplicates/{task_id}/move")
async def api_move_duplicates(task_id: str, request: MoveDuplicatesRequest):
    """Move duplicate files to a quarantine folder instead of deleting them."""
    # Try memory first, then database
    duplicate_result = _duplicate_results.get(task_id)
    if not duplicate_result:
        with get_db() as conn:
            duplicate_result = get_duplicate_scan(conn, task_id)
    
    if not duplicate_result:
        raise HTTPException(
            status_code=404, 
            detail="Duplicate scan result not found. Run /duplicates first or scan may have expired."
        )
    
    if not request.destination_folder:
        raise HTTPException(
            status_code=400,
            detail="Destination folder is required"
        )
    
    try:
        result = move_duplicates(
            duplicate_result,
            destination_folder=request.destination_folder,
            use_hash=request.use_hash,
            use_metadata=request.use_metadata,
            dry_run=request.dry_run,
            preserve_structure=request.preserve_structure
        )
        return result
    except Exception as e:
        logger.exception(f"Move duplicates failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/scans")
async def api_list_duplicate_scans(limit: int = 20):
    """List recent duplicate scans."""
    try:
        with get_db() as conn:
            scans = list_duplicate_scans(conn, limit)
        return {"scans": scans}
    except Exception as e:
        logger.exception(f"Failed to list duplicate scans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/{scan_id}")
async def api_get_duplicate_scan(scan_id: str):
    """Get a specific duplicate scan result."""
    # Try memory first
    result = _duplicate_results.get(scan_id)
    if result:
        return result
    
    # Try database
    try:
        with get_db() as conn:
            result = get_duplicate_scan(conn, scan_id)
        if not result:
            raise HTTPException(status_code=404, detail="Duplicate scan not found")
        
        # Cache in memory for future requests
        _duplicate_results[scan_id] = result
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get duplicate scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/duplicates/{scan_id}")
async def api_delete_duplicate_scan_record(scan_id: str):
    """Delete a duplicate scan record from database."""
    try:
        with get_db() as conn:
            deleted = delete_duplicate_scan(conn, scan_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Duplicate scan not found")
        
        # Remove from memory cache if present
        _duplicate_results.pop(scan_id, None)
        return {"status": "deleted", "scan_id": scan_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete duplicate scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of an organize task."""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/create-folders")
async def api_create_folders(dest: str):
    """Create folder structure from folder_mapping.json."""
    if not Path(dest).is_dir():
        raise HTTPException(status_code=400, detail=f"Destination not found: {dest}")
    try:
        return create_folder_structure(dest)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-empty")
async def api_cleanup_empty(directory: str):
    """Remove empty folders recursively."""
    if not Path(directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
    try:
        removed = cleanup_empty_folders(directory)
        return {"removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Background tasks ──────────────────────────────────────────────────────────

async def _run_plan(task_id: str, source: str, dest: str, recursive: bool = True):
    """Background task for planning organization."""
    loop = asyncio.get_event_loop()
    mode = "recursive" if recursive else "top-level only"
    await manager.send_status(task_id, "started", f"Planning ({mode}): {source} → {dest}")

    try:
        def progress_cb(current, total):
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, current, total, f"Scanning: {current}/{total}"),
                loop,
            )

        plan = await loop.run_in_executor(
            None, lambda: plan_organize(source, dest, recursive=recursive, progress_callback=progress_cb)
        )

        _plans[plan.plan_id] = plan
        result = plan.to_dict()

        _tasks[task_id] = {"status": "completed", "type": "plan", "result": result}
        await manager.send_result(task_id, result)
        await manager.send_status(task_id, "completed", f"Plan ready: {plan.files_to_move} files to move")

    except Exception as e:
        logger.exception(f"Plan failed: {e}")
        _tasks[task_id] = {"status": "error", "type": "plan", "error": str(e)}
        await manager.send_status(task_id, "error", str(e))


async def _run_execute(task_id: str, plan: OrganizePlan):
    """Background task for executing a plan."""
    loop = asyncio.get_event_loop()
    await manager.send_status(task_id, "started", f"Executing plan {plan.plan_id}...")

    try:
        def progress_cb(current, total):
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, current, total, f"Moving: {current}/{total}"),
                loop,
            )

        result = await loop.run_in_executor(
            None, lambda: execute_plan(plan, progress_callback=progress_cb)
        )

        _tasks[task_id] = {"status": "completed", "type": "execute", "result": result}
        await manager.send_result(task_id, result)
        await manager.send_status(task_id, "completed", f"Done: {result['files_moved']} moved")

    except Exception as e:
        logger.exception(f"Execute failed: {e}")
        _tasks[task_id] = {"status": "error", "type": "execute", "error": str(e)}
        await manager.send_status(task_id, "error", str(e))


async def _run_clean_names(task_id: str, directory: str, dry_run: bool):
    """Background task for cleaning file names."""
    loop = asyncio.get_event_loop()
    await manager.send_status(task_id, "started", f"Cleaning names in {directory}...")

    try:
        def progress_cb(current, total):
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, current, total, f"Cleaning: {current}/{total}"),
                loop,
            )

        result = await loop.run_in_executor(
            None, lambda: clean_directory(directory, dry_run=dry_run, progress_callback=progress_cb)
        )

        _tasks[task_id] = {"status": "completed", "type": "clean-names", "result": result}
        await manager.send_result(task_id, result)
        await manager.send_status(task_id, "completed", f"Done: {result['total_renamed']} files")

    except Exception as e:
        logger.exception(f"Clean names failed: {e}")
        _tasks[task_id] = {"status": "error", "type": "clean-names", "error": str(e)}
        await manager.send_status(task_id, "error", str(e))


async def _run_duplicates(task_id: str, source: str, against: str | None):
    """Background task for duplicate detection."""
    loop = asyncio.get_event_loop()
    await manager.send_status(task_id, "started", f"Scanning duplicates in {source}...")

    try:
        def progress_cb(current, total):
            asyncio.run_coroutine_threadsafe(
                manager.send_progress(task_id, current, total, f"Hashing: {current}/{total}"),
                loop,
            )

        result = await loop.run_in_executor(
            None, lambda: find_duplicates(source, against=against, progress_callback=progress_cb)
        )

        # Store result in memory for immediate access
        _duplicate_results[task_id] = result
        
        # Persist result to database
        with get_db() as conn:
            save_duplicate_scan(conn, task_id, source, against, result)
        
        _tasks[task_id] = {"status": "completed", "type": "duplicates", "result": result}
        await manager.send_result(task_id, result)
        await manager.send_status(task_id, "completed", f"Done: {result['total_hash_groups']} hash groups")

    except Exception as e:
        logger.exception(f"Duplicates scan failed: {e}")
        _tasks[task_id] = {"status": "error", "type": "duplicates", "error": str(e)}
        await manager.send_status(task_id, "error", str(e))
