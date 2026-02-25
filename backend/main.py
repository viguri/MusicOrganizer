"""Music Organizer — FastAPI backend entry point."""

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.config import (
    CORS_ORIGINS,
    API_HOST,
    API_PORT,
    DEFAULT_STYLES_DIR,
    DEFAULT_NEW_RELEASES_DIR,
    DEFAULT_MASTER_COLLECTION,
    TARGET_FOLDER_COUNT,
)
from backend.api.websocket import manager
from backend.api.routes_scan import router as scan_router
from backend.api.routes_organize import router as organize_router
from backend.api.routes_settings import router as settings_router
from backend.api.routes_rekordbox import router as rekordbox_router
from backend.modules.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Music Organizer",
    description="Automate music organization, genre classification, and Rekordbox sync",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(scan_router, prefix="/api")
app.include_router(organize_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(rekordbox_router, prefix="/api")


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()
    logger.info("Music Organizer backend started")


@app.get("/api/health")
async def health():
    """Health check."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    return {
        "styles_dir": DEFAULT_STYLES_DIR,
        "new_releases_dir": DEFAULT_NEW_RELEASES_DIR,
        "master_collection": DEFAULT_MASTER_COLLECTION,
        "target_folder_count": TARGET_FOLDER_COUNT,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=API_HOST, port=API_PORT, reload=True)
