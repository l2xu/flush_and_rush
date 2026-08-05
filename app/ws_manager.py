import asyncio
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

_LOGGER = logging.getLogger(__name__)


class GuestConnectionManager:
    """Haelt aktive Guest-WebSocket-Verbindungen und verteilt Live-Updates."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)

        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:  # pragma: no cover
                _LOGGER.debug("Guest-WebSocket send fehlgeschlagen, entferne Verbindung")
                await self.disconnect(websocket)
