from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
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
local_rate_cache = {}

_db_write_queue: asyncio.Queue = None
_db_enabled = False


async def _init_db():
    """Initialize PostgreSQL schema: drop old table if exists, create fresh."""
    try:
        async with engine.begin() as conn:
            # Drop old table (safe: data accumulates from collectors)
            await conn.execute(text("DROP TABLE IF EXISTS funding_rates CASCADE"))
            await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL table initialized (funding_interval)")
        return True
    except Exception as e:
        logger.warning(f"PostgreSQL init failed: {e}")
        return False


async def _db_writer():
    """Background task: batch-writes funding rate data to PostgreSQL."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    global _db_write_queue, _db_enabled
    _db_write_queue = asyncio.Queue(maxsize=50000)

    if not await _init_db():
        return  # DB unavailable — continue without it

    _db_enabled = True

    while _db_enabled:
        batch = []
        try:
            while len(batch) < 50:
                try:
                    item = await asyncio.wait_for(_db_write_queue.get(), timeout=2)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break
            if batch:
                async with SessionLocal() as session:
                    stmt = pg_insert(FundingRate).values(batch)
                    stmt = stmt.on_conflict_do_nothing()
                    await session.execute(stmt)
                    await session.commit()
        except Exception as e:
            logger.error(f"DB write error: {e}")


async def db_callback(data):
    """Redis + PostgreSQL 寫入"""
    global redis
    if redis is None: return

    items = data if isinstance(data, list) else [data]
    mset_data = {}
    db_rows = []

    for item in items:
        exch = item['exchange'].lower()
        sym = item['symbol'].upper().replace("-", "").replace("_", "")
        key = f"latest:{exch}:{sym}"

        redis_data = item.copy()
        if isinstance(redis_data.get('settlement_time'), datetime):
            redis_data['settlement_time'] = redis_data['settlement_time'].isoformat()
        if isinstance(redis_data.get('timestamp'), datetime):
            redis_data['timestamp'] = redis_data['timestamp'].isoformat()
        mset_data[key] = json.dumps(redis_data)

        db_rows.append({
            "exchange": exch,
            "symbol": sym,
            "timestamp": datetime.utcnow(),
            "rate": float(item['rate']),
            "funding_interval": item.get('interval', 8),
            "settlement_time": item.get('settlement_time') if isinstance(item.get('settlement_time'), datetime) else None,
        })

    if mset_data:
        await redis.mset(mset_data)

    if _db_write_queue is not None:
        for row in db_rows:
            try:
                _db_write_queue.put_nowait(row)
            except asyncio.QueueFull:
                break


async def ws_callback(data):
    await ws_manager.broadcast(data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", decode_responses=True)

    asyncio.create_task(_db_writer())
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
