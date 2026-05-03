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
db_queue = asyncio.Queue()
local_rate_cache = {} # v11.8: 本地緩存，減少 Redis 壓力

async def db_worker():
    while True:
        items = []
        try:
            item = await db_queue.get()
            items.append(item)
            while len(items) < 100:
                try:
                    item = await asyncio.wait_for(db_queue.get(), timeout=1.0)
                    items.append(item)
                except asyncio.TimeoutError: break
        except Exception: continue
        if items:
            async with SessionLocal() as session:
                try:
                    for data in items:
                        new_rate = FundingRate(
                            exchange=data["exchange"], symbol=data["symbol"], rate=data["rate"],
                            settlement_time=data["settlement_time"], timestamp=data["timestamp"]
                        )
                        session.add(new_rate)
                    await session.commit()
                except Exception as e: logger.error(f"DB Error: {e}")
                finally:
                    for _ in range(len(items)): db_queue.task_done()

async def db_callback(data):
    """資料庫與 Redis 寫入 Callback (極速批次版)"""
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

            # 更新本地 Cache 用於過濾 DB 寫入
            current_rate = item['rate']
            last_rate = local_rate_cache.get(key)
            if last_rate is None or abs(last_rate - current_rate) > 1e-9:
                await db_queue.put(item)
                local_rate_cache[key] = current_rate

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

        current_rate = data['rate']
        last_rate = local_rate_cache.get(key)
        if last_rate is None or abs(last_rate - current_rate) > 1e-9:
            await db_queue.put(data)
            local_rate_cache[key] = current_rate


async def ws_callback(data):
    await ws_manager.broadcast(data)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", decode_responses=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS funding_rates (exchange VARCHAR, symbol VARCHAR, rate DOUBLE PRECISION, settlement_time TIMESTAMP, timestamp TIMESTAMP, PRIMARY KEY (exchange, symbol, timestamp)) PARTITION BY RANGE (timestamp);"))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS funding_rates_default PARTITION OF funding_rates DEFAULT;"))
    
    asyncio.create_task(db_worker())
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
