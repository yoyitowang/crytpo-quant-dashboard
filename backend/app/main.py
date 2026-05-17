from fastapi import FastAPI
from contextlib import asynccontextmanager
from backend.app.core.config import settings
from backend.app.api import endpoints
from backend.app.services.collector import collector
from backend.app.models.funding_rate import FundingRate
from backend.app.db.session import SessionLocal
from backend.app.services.websocket_manager import ws_manager
from backend.app.dependencies import set_redis, get_redis
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import structlog
from datetime import datetime, timedelta, timezone
from redis import asyncio as aioredis
from redis.exceptions import ReadOnlyError
from prometheus_fastapi_instrumentator import Instrumentator
from backend.app.metrics import ws_active_connections, db_writer_queue_size, collector_circuit_open

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.ENV == "dev" else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

local_rate_cache = {}

_db_write_queue: asyncio.Queue = None
_db_enabled = False


async def _init_db():
    """Apply Alembic migrations on startup. Never drops data."""
    from alembic.config import Config
    from alembic.command import upgrade, stamp
    alembic_cfg = Config("backend/alembic.ini")
    try:
        await asyncio.wait_for(
            asyncio.to_thread(upgrade, alembic_cfg, "head"),
            timeout=15
        )
        logger.info("database schema up to date (alembic migration applied)")
        return True
    except Exception as e:
        logger.warning("migration upgrade failed, trying stamp head", error=str(e)[:200])
        try:
            await asyncio.wait_for(
                asyncio.to_thread(stamp, alembic_cfg, "head"),
                timeout=10
            )
            logger.info("database schema stamped (existing schema matches migration)")
        except Exception as e2:
            logger.error("database migration completely failed", error=str(e2)[:200])
        return True


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
                    stmt = stmt.on_conflict_do_update(
                        constraint="funding_rates_pkey",
                        set_={"rate": stmt.excluded.rate, "funding_interval": stmt.excluded.funding_interval, "settlement_time": stmt.excluded.settlement_time}
                    )
                    await session.execute(stmt)
                    await session.commit()
        except Exception as e:
            err_str = str(e)
            if "no partition" in err_str or "does not exist" in err_str or "UndefinedColumn" in err_str:
                logger.error("db schema error — disabling writes", error=err_str[:200])
                _db_enabled = False
            else:
                logger.error("db write error", error=err_str[:200])


async def _metrics_loop():
    while True:
        await asyncio.sleep(15)
        ws_active_connections.set(len(ws_manager.active_connections))
        db_writer_queue_size.set(_db_write_queue.qsize() if _db_write_queue else 0)
        for name, cb in collector.circuit_breakers.items():
            collector_circuit_open.labels(exchange=name).set(1 if cb.is_open else 0)

        redis = get_redis()
        if redis is None:
            try:
                r = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", decode_responses=True, socket_connect_timeout=3)
                await r.ping()
                set_redis(r)
                logger.info("redis_reconnected")
            except Exception:
                pass


async def db_callback(data):
    """Redis + PostgreSQL 寫入"""
    redis = get_redis()
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

        settle = item.get('settlement_time')
        interval = item.get('interval', 8)
        db_ts = settle - timedelta(hours=interval) if isinstance(settle, datetime) else datetime.now(timezone.utc)

        db_rows.append({
            "exchange": exch,
            "symbol": sym,
            "timestamp": db_ts,
            "rate": float(item['rate']),
            "funding_interval": interval,
            "settlement_time": settle if isinstance(settle, datetime) else None,
        })

    if mset_data:
        try:
            await redis.mset(mset_data)
        except ReadOnlyError:
            logger.error("redis_readonly — clearing connection, ws + db still work")
            set_redis(None)
        except Exception as e:
            logger.error("redis_mset_failed", error=str(e)[:200])

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
    r = aioredis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", decode_responses=True)
    set_redis(r)

    asyncio.create_task(_db_writer())
    collector.register_callback(db_callback)
    collector.register_callback(ws_callback)
    collector_task = asyncio.create_task(collector.start())
    asyncio.create_task(_metrics_loop())
    yield
    collector_task.cancel()
    await r.close()
    set_redis(None)

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/api/metrics")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(endpoints.router, prefix="/api")

@app.get("/")
async def root(): return {"message": "Active"}
