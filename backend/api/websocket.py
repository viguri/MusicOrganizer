"""WebSocket connection manager for real-time progress updates."""

import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts progress updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return
        data = json.dumps(message)
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)

    async def send_progress(self, task_id: str, current: int, total: int, detail: str = ""):
        """Send a progress update."""
        await self.broadcast({
            "type": "progress",
            "task_id": task_id,
            "current": current,
            "total": total,
            "percent": round((current / total) * 100, 1) if total > 0 else 0,
            "detail": detail,
        })

    async def send_status(self, task_id: str, status: str, message: str = ""):
        """Send a status update (started, completed, error)."""
        await self.broadcast({
            "type": "status",
            "task_id": task_id,
            "status": status,
            "message": message,
        })

    async def send_result(self, task_id: str, data: Dict):
        """Send a task result."""
        await self.broadcast({
            "type": "result",
            "task_id": task_id,
            "data": data,
        })


# Singleton instance
manager = ConnectionManager()
