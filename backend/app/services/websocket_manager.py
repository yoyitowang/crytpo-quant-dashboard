from fastapi import WebSocket
from typing import List, Dict, Any
import json
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.broadcast_count = 0
        self.batch_queue = []
        self.lock = asyncio.Lock()
        self.is_flushing = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

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
            await asyncio.sleep(1.0) # 1 second batching window
            
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

    async def _send_batch(self, batch: List[Any]):
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return super().default(obj)

        try:
            encoded_msg = json.dumps(batch, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Broadcast Encode Error: {e}")
            return
        
        self.broadcast_count += 1
        if self.broadcast_count % 10 == 0:
            logger.info(f"Broadcast Check: Sent batch {self.broadcast_count} (size: {len(batch)}) to {len(self.active_connections)} clients.")

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(encoded_msg)
            except Exception:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()
