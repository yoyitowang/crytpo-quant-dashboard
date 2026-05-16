from fastapi import WebSocket
from typing import List, Dict, Any
import json
import structlog
import asyncio
from datetime import datetime

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.broadcast_count = 0
        self.batch_queue = []
        self.lock = asyncio.Lock()
        self.is_flushing = False
        self._heartbeat_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("client_connected", total=len(self.active_connections))
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("client_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: Any):
        if not self.active_connections:
            return

        async with self.lock:
            if isinstance(message, list):
                self.batch_queue.extend(message)
            else:
                self.batch_queue.append(message)

            if not self.is_flushing:
                self.is_flushing = True
                asyncio.create_task(self._periodic_flush())

    async def _periodic_flush(self):
        while True:
            await asyncio.sleep(1.0)

            async with self.lock:
                if not self.batch_queue:
                    if not self.active_connections:
                        self.is_flushing = False
                        break
                    continue

                batch = self.batch_queue
                self.batch_queue = []

            await self._send_batch(batch)

            if not self.active_connections:
                self.is_flushing = False
                break

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(30)
            if not self.active_connections:
                self._heartbeat_task = None
                break
            stale = []
            for ws in self.active_connections:
                try:
                    await asyncio.wait_for(ws.send_json({"type": "ping"}), timeout=5)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                logger.warning("heartbeat_removing_stale", total=len(self.active_connections))
                self.disconnect(ws)

    async def _send_batch(self, batch: List[Any]):
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return super().default(obj)

        try:
            encoded_msg = json.dumps(batch, cls=DateTimeEncoder)
        except Exception as e:
            logger.error("broadcast_encode_error", error=str(e)[:200])
            return

        self.broadcast_count += 1
        if self.broadcast_count % 10 == 0:
            logger.info("broadcast_check", batch_count=self.broadcast_count, size=len(batch), clients=len(self.active_connections))

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(encoded_msg)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


ws_manager = ConnectionManager()
