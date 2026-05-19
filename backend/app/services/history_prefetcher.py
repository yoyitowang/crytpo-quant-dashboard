"""Background history prefetcher — warms Redis cache for ALL tracked symbols.
Runs immediately at startup then every hour. Skips symbols already cached.
"""
import asyncio
import structlog
from typing import Set, Tuple

logger = structlog.get_logger()

_PREFETCH_INTERVAL = 3600  # 1 hour
_PREFETCH_SEM = asyncio.Semaphore(10)
_PER_SYMBOL_TIMEOUT = 25  # longer than user-facing timeout (background work)
_OVERALL_TIMEOUT = 300    # 5 min max per cycle


async def _get_tracked_pairs() -> Set[Tuple[str, str]]:
    """Get all (exchange, symbol) pairs currently tracked by the collector."""
    from backend.app.services.collector import collector
    pairs: Set[Tuple[str, str]] = set()
    for key, item in collector.latest_rates.items():
        exch = item.get('exchange', '').lower()
        sym = item.get('symbol', '').upper()
        if exch and sym:
            pairs.add((exch, sym))
    return pairs


async def run_prefetch():
    """Prefetch ALL active (exchange, symbol) pairs into Redis cache."""
    from backend.app.api.endpoints import _live_fetch, _store_history_batch
    from backend.app.dependencies import get_redis

    redis = get_redis()
    pairs = await _get_tracked_pairs()
    if not pairs:
        logger.warning("prefetch_skip_no_symbols")
        return

    logger.info("prefetch_start", total=len(pairs))

    async def prefetch_one(exchange: str, symbol: str):
        for days in (3, 7, 14, 30):
            cache_key = f"history:{exchange}:{symbol}:{days}"
            if redis:
                try:
                    if await redis.get(cache_key):
                        continue
                except Exception:
                    pass

            async with _PREFETCH_SEM:
                try:
                    data = await asyncio.wait_for(
                        _live_fetch(exchange, symbol, days=days),
                        timeout=_PER_SYMBOL_TIMEOUT
                    )
                    if data:
                        await _store_history_batch(exchange, symbol, data)
                    if redis:
                        await redis.setex(cache_key, 3600, json.dumps(data or []))
                    logger.debug("prefetch_ok", exchange=exchange, symbol=symbol, days=days, count=len(data) if data else 0)
                except asyncio.TimeoutError:
                    logger.debug("prefetch_timeout", exchange=exchange, symbol=symbol, days=days)
                except Exception as e:
                    logger.debug("prefetch_skip", exchange=exchange, symbol=symbol, days=days, error=str(e)[:100])

    import json
    tasks = [asyncio.create_task(prefetch_one(ex, sym)) for ex, sym in pairs]
    done, pending = await asyncio.wait(tasks, timeout=_OVERALL_TIMEOUT)
    for t in pending:
        t.cancel()
    logger.info("prefetch_done", ok=len(done), timeout=len(pending))


async def prefetch_loop():
    """Background loop: immediate prefetch → every 1h."""
    await asyncio.sleep(15)  # wait for collector to populate
    try:
        await run_prefetch()
    except Exception as e:
        logger.error("prefetch_initial_failed", error=str(e)[:200])

    while True:
        await asyncio.sleep(_PREFETCH_INTERVAL)
        try:
            await run_prefetch()
        except Exception as e:
            logger.error("prefetch_cycle_failed", error=str(e)[:200])
