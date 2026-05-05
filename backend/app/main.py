from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.api import endpoints
from backend.app.services.collector import collector
from backend.app.models.funding_rate import FundingRate, Base
from backend.app.db.session import SessionLocal, engine
from backend.app.services.websocket_manager import ws_manager
from redis import asyncio as aioredis
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

redis: aioredis.Redis = None
local_rate_cache = {} # v11.8: 本地緩存，減少 Redis 壓力

async def db_callback(data):
    """Redis 寫入 Callback (極速批次版) - 已移除 PostgreSQL 寫入以降低負擔"""
    global redis
    if redis is None: return

    if isinstance(data, list):
        # --- 核心優化：針對 Binance 等巨量資料使用 MSET ---
        mset_data = {}
        for item in data:
            exch = item['exchange'].lower()
            sym = item['symbol'].upper().replace("-", "").replace("_", "")
            key = f"latest:{exch}:{sym}"

            # 序列化
            redis_data = item.copy()
            redis_data['settlement_time'] = redis_data['settlement_time'].isoformat() if isinstance(redis_data.get('settlement_time'), datetime) else redis_data.get('settlement_time')
            redis_data['timestamp'] = redis_data['timestamp'].isoformat() if isinstance(redis_data.get('timestamp'), datetime) else redis_data.get('timestamp')
            mset_data[key] = json.dumps(redis_data)
        
        if mset_data:
            await redis.mset(mset_data)
    else:
        # 單筆資料處理
        exch = data['exchange'].lower()
        sym = data['symbol'].upper().replace("-", "").replace("_", "")
        key = f"latest:{exch}:{sym}"
        redis_data = data.copy()
        redis_data['settlement_time'] = redis_data['settlement_time'].isoformat() if isinstance(redis_data.get('settlement_time'), datetime) else redis_data.get('settlement_time')
        redis_data['timestamp'] = redis_data['timestamp'].isoformat() if isinstance(redis_data.get('timestamp'), datetime) else redis_data.get('timestamp')

        await redis.set(key, json.dumps(redis_data))

async def ws_callback(data):
    await ws_manager.broadcast(data)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", decode_responses=True)
    
    # 歷史資金費率已全面改為 API 動態抓取，不再初始化本地資料庫表
    collector.register_callback(db_callback)
    collector.register_callback(ws_callback)
    collector_task = asyncio.create_task(collector.start())
    yield
    collector_task.cancel()
    await redis.close()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(endpoints.router, prefix="/api")

@app.get("/")
async def root(): return {"message": "Active"}
