from fastapi import WebSocket
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        # Convert datetime objects to string for JSON serialization
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                from datetime import datetime
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return super().default(obj)

        try:
            encoded_msg = json.dumps(message, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Failed to encode broadcast message: {e}")
            return
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(encoded_msg)
            except Exception:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()
