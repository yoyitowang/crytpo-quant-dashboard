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

async def db_worker():
    """專門負責將費率變動批次寫入資料庫，防止阻塞。"""
    while True:
        items = []
        try:
            # 等待第一筆資料
            item = await db_queue.get()
            items.append(item)
            # 嘗試獲取更多資料直到 100 筆或超時
            while len(items) < 100:
                try:
                    item = await asyncio.wait_for(db_queue.get(), timeout=1.0)
                    items.append(item)
                except asyncio.TimeoutError:
                    break
        except Exception: continue
        
        if items:
            async with SessionLocal() as session:
                try:
                    for data in items:
                        new_rate = FundingRate(
                            exchange=data["exchange"],
                            symbol=data["symbol"],
                            rate=data["rate"],
                            settlement_time=data["settlement_time"],
                            timestamp=data["timestamp"]
                        )
                        session.add(new_rate)
                    await session.commit()
                except Exception as e:
                    logger.error(f"DB Batch Write Error: {e}")
                finally:
                    for _ in range(len(items)): db_queue.task_done()

async def db_callback(data):
    """Callback to save funding rate to database and Redis."""
    global redis
    if redis is None: return
    
    # 1. 永遠存入 Redis (Latest State) - 最優先
    key = f"latest:{data['exchange']}:{data['symbol']}"
    redis_data = data.copy()
    redis_data['settlement_time'] = redis_data['settlement_time'].isoformat() if redis_data['settlement_time'] else None
    redis_data['timestamp'] = redis_data['timestamp'].isoformat()
    await redis.set(key, json.dumps(redis_data))

    # 2. 費率變動才進 DB 隊列
    hist_key = f"last_rate:{data['exchange']}:{data['symbol']}"
    last_rate_val = await redis.get(hist_key)
    
    if last_rate_val is None or abs(float(last_rate_val) - data["rate"]) > 1e-9:
        await db_queue.put(data)
        await redis.set(hist_key, str(data["rate"]))

async def ws_callback(data):
    """Callback to broadcast funding rate to all connected clients."""
    safe_data = data.copy()
    if safe_data.get('settlement_time'):
        safe_data['settlement_time'] = safe_data['settlement_time'].isoformat()
    if safe_data.get('timestamp'):
        safe_data['timestamp'] = safe_data['timestamp'].isoformat()
    await ws_manager.broadcast(safe_data)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", decode_responses=True)
    
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                exchange VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                rate DOUBLE PRECISION,
                settlement_time TIMESTAMP,
                timestamp TIMESTAMP NOT NULL,
                PRIMARY KEY (exchange, symbol, timestamp)
            ) PARTITION BY RANGE (timestamp);
        """))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS funding_rates_default PARTITION OF funding_rates DEFAULT;"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_funding_lookup ON funding_rates (exchange, symbol, timestamp DESC);"))
    
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
async def root():
    return {"message": "Crypto Funding Rate API is running"}
