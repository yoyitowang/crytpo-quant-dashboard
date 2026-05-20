from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Response, Query
from backend.app.services.collector import collector
from backend.app.services.websocket_manager import ws_manager
from backend.app.db.session import SessionLocal
from backend.app.models.funding_rate import FundingRate
from backend.app.models.spread_snapshot import SpreadSnapshot
from backend.app.services.aden_api import fetch_funding_rate_history as aden_fetch_history
from backend.app.dependencies import get_redis, get_symbol_inventory
from typing import Dict, List, Optional
import structlog
import json
import re
import asyncio
from datetime import datetime, timedelta, timezone
import ccxt.async_support as ccxt_async
import ccxt as ccxt_sync
from sqlalchemy import select, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert

_HISTORY_CACHE_TTL = 3600  # 1 hour — history data does not change


def _deduplicate_settlement(data: list) -> list:
    """Keep only one data point per (year, month, day, hour) bucket.
    This ensures only settlement-time rates are stored (one per funding period).
    For 1h, 4h, 8h funding intervals, each settlement falls in a distinct hour bucket.
    Sorts by timestamp first so the latest entry per bucket wins.
    """
    if not data:
        return []
    buckets: Dict[str, dict] = {}
    sorted_data = sorted(data, key=lambda x: x.get("timestamp", ""))
    for item in sorted_data:
        ts_str = item["timestamp"]
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        key = dt.strftime("%Y-%m-%dT%H")
        buckets[key] = item
    return list(buckets.values())


async def _store_history_batch(exchange: str, symbol: str, data: list):
    """Upsert history funding rate data to PostgreSQL for persistent storage.
    Primary key: (exchange, symbol, timestamp) — conflicts update the rate.
    """
    if not data:
        return
    clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()
    rows = []
    for item in _deduplicate_settlement(data):
        ts_str = item["timestamp"]
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        rows.append({
            "exchange": exchange.lower(),
            "symbol": clean_sym,
            "timestamp": ts,
            "rate": float(item["rate"]),
            "funding_interval": 8,
        })
    if not rows:
        return
    try:
        async with SessionLocal() as session:
            stmt = pg_insert(FundingRate).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="funding_rates_pkey",
                set_={"rate": stmt.excluded.rate},
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as e:
        logger.debug("store_history_failed", exchange=exchange, error=str(e)[:100])

router = APIRouter()
logger = structlog.get_logger()

async def get_history_from_db(exchange: str, symbol: str, days: int) -> list:
    """Query funding rate history from local PostgreSQL (fast, no external API)."""
    clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        async with SessionLocal() as session:
            stmt = select(FundingRate).where(
                FundingRate.exchange == exchange.lower(),
                FundingRate.symbol == clean_sym,
                FundingRate.timestamp >= since
            ).order_by(FundingRate.timestamp.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            if rows:
                return [{"timestamp": r.timestamp.replace(tzinfo=timezone.utc).isoformat(), "rate": r.rate} for r in rows]
    except Exception as e:
        logger.debug("db read unavailable", exchange=exchange, symbol=symbol)
    return []

@router.get("/rates/compressed")
async def get_compressed_rates():
    """極簡版數據介面，專供前端快速渲染矩陣使用，移除不必要的欄位與冗餘計算。"""
    try:
        redis = get_redis()
        if redis is None: return []
        keys = await redis.keys("latest:*")
        if not keys: return []
        
        # 分批獲取以防止 Redis 阻塞
        all_data = []
        for i in range(0, len(keys), 1000):
            batch_keys = keys[i:i+1000]
            rates_json = await redis.mget(batch_keys)
            all_data.extend([json.loads(r) for r in rates_json if r])
            
        # 壓縮：只保留 symbol, exchange, rate, interval, mark_price
        compressed = []
        for r in all_data:
            compressed.append([
                r['symbol'],
                r['exchange'],
                round(r['rate'], 6),
                r.get('interval', 8),
                r.get('mark_price')
            ])
        return compressed
    except Exception as e:
        logger.error("compressed rates error", error=str(e)[:200])
        return []

@router.get("/health/live")
async def health_live():
    return Response(status_code=200, content="ok")

@router.get("/health/ready")
async def health_ready():
    redis = get_redis()
    issues = []
    if redis is None:
        issues.append("redis unavailable")
    else:
        try:
            await redis.ping()
        except Exception:
            issues.append("redis unreachable")
    from backend.app.main import _db_enabled
    if not _db_enabled:
        issues.append("db writes disabled")
    latest_ts = "None"
    if collector.latest_rates:
        ts_list = [r['timestamp'] for r in collector.latest_rates.values() if isinstance(r.get('timestamp'), datetime)]
        if ts_list:
            latest_ts = max(ts_list).isoformat()
    circuit_states = collector.get_circuit_states()
    open_circuits = [name for name, st in circuit_states.items() if st == "open"]
    if open_circuits:
        issues.append(f"circuit_open: {','.join(open_circuits)}")
    status_code = 200 if not issues else 503
    return Response(
        status_code=status_code,
        content=json.dumps({
            "status": "ok" if not issues else "degraded",
            "issues": issues,
            "last_update": latest_ts,
            "active_exchanges": list(collector.exchanges.keys()),
            "symbols_tracked": len(collector.latest_rates),
            "circuit_breakers": circuit_states
        }),
        media_type="application/json"
    )

@router.get("/rates/latest")
async def get_latest_rates():
    try:
        redis = get_redis()
        if redis is None: return []
        keys = await redis.keys("latest:*")
        if not keys: return []
        rates_json = await redis.mget(keys)
        return [json.loads(r) for r in rates_json if r]
    except Exception as e:
        logger.error("error fetching latest", error=str(e)[:200])
        return []

@router.get("/analysis/summary")
async def get_market_summary():
    try:
        redis = get_redis()
        if redis is None: return {}
        keys = await redis.keys("latest:*")
        if not keys: return {}
        rates_json = await redis.mget(keys)
        all_rates = [json.loads(r) for r in rates_json if r]
        if not all_rates: return {}
        
        # Calculate APR for each symbol: rate * (24/interval) * 365
        for r in all_rates:
            interval = r.get('interval', 8)
            r['apr'] = r['rate'] * (24 / interval) * 365
            
        avg_rate = sum(r['rate'] for r in all_rates) / len(all_rates)
        avg_apr = sum(r['apr'] for r in all_rates) / len(all_rates)
        
        sorted_rates = sorted(all_rates, key=lambda x: x['rate'])
        top_neg = sorted_rates[:5]
        top_pos = sorted_rates[-5:][::-1]
        
        usdt_rates = [r['rate'] for r in all_rates if 'USDT' in r['symbol']]
        usdc_rates = [r['rate'] for r in all_rates if 'USDC' in r['symbol']]
        avg_usdt = sum(usdt_rates) / len(usdt_rates) if usdt_rates else 0
        avg_usdc = sum(usdc_rates) / len(usdc_rates) if usdc_rates else 0
        
        return {
            "market_sentiment": "Bullish" if avg_apr > 0 else "Bearish",
            "avg_funding_rate": avg_rate,
            "avg_apr": avg_apr,
            "top_positive": top_pos,
            "top_negative": top_neg,
            "stablecoin_stats": { "usdt_avg": avg_usdt, "usdc_avg": avg_usdc },
            "total_symbols": len(all_rates)
        }
    except Exception as e:
        logger.error("summary error", error=str(e)[:200])
        return {}

import aiohttp

async def fetch_coinw_history(symbol: str, days: int):
    """專屬 CoinW 歷史 API 抓取邏輯（含多 domain fallback）"""
    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
    base = match.group(1).lower() if match else symbol.lower()
    
    urls = [
        ("POST", f"https://futuresapi.faefrdpenn.com/v1/futuresc/public/selectFundingRateHistory", {"instrument": base, "day": days}),
        ("GET", f"https://api.coinw.com/v1/perpum/fundingRateHistory?instrument={base}&day={days}", None),
    ]
    
    for method, url, payload in urls:
        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"timeout": 10}
                if method == "POST":
                    kwargs["json"] = payload
                    kwargs["headers"] = {"Content-Type": "application/json"}
                async with session.request(method, url, **kwargs) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = None
                        if isinstance(data, dict) and data.get('code') == 0:
                            items = data.get('data', [])
                        elif isinstance(data, list):
                            items = data
                        if items:
                            return [
                                {
                                    "timestamp": datetime.strptime(item['createdDate'], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).isoformat(),
                                    "rate": float(item['fundingRate'])
                                } for item in items
                            ]
        except Exception:
            continue
    logger.warning("coinw_history_unavailable", symbol=symbol)
    return []

_lighter_market_cache: dict = {"data": None, "time": 0}
_LIGHTER_CACHE_TTL = 300

async def fetch_lighter_history(symbol: str, days: int) -> list:
    """Lighter 官方 API 抓取歷史資金費率。
    https://apidocs.lighter.xyz/reference/fundings
    """
    base = re.sub(r'(USDT|USDC)$', '', symbol, flags=re.IGNORECASE).upper()

    try:
        async with aiohttp.ClientSession() as session:
            # 1. 獲取 market_id (快取 5 分鐘)
            market_id = None
            now_ts = datetime.now(timezone.utc).timestamp()
            if _lighter_market_cache["data"] is None or now_ts - _lighter_market_cache["time"] > _LIGHTER_CACHE_TTL:
                async with session.get(
                    "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates",
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 200:
                            _lighter_market_cache["data"] = data["funding_rates"]
                            _lighter_market_cache["time"] = now_ts

            if _lighter_market_cache["data"]:
                for item in _lighter_market_cache["data"]:
                    if item.get("exchange") == "lighter" and item.get("symbol", "").upper() == base:
                        market_id = item["market_id"]
                        break

            if market_id is None:
                logger.warning("lighter_market_not_found", symbol=symbol, base=base)
                return []

            # 2. 取得歷史 funding 資料
            now = int(datetime.now(timezone.utc).timestamp())
            since = now - days * 86400
            async with session.get(
                "https://mainnet.zklighter.elliot.ai/api/v1/fundings",
                params={
                    "market_id": market_id,
                    "resolution": "1h",
                    "start_timestamp": since,
                    "end_timestamp": now,
                    "count_back": 1000,
                },
                timeout=15
            ) as resp:
                if resp.status != 200:
                    return []
                hist = await resp.json()
                if hist.get("code") != 200:
                    return []

                result = []
                for f in hist.get("fundings", []):
                    rate = float(f["rate"])
                    if rate == 0:
                        continue
                    direction = f.get("direction", "long")
                    # direction "short" → shorts pay longs → rate negative in our convention
                    signed_rate = rate if direction == "long" else -rate
                    result.append({
                        "timestamp": datetime.fromtimestamp(f["timestamp"], tz=timezone.utc).isoformat(),
                        "rate": signed_rate
                    })

                if result:
                    result.sort(key=lambda x: x["timestamp"])
                return result
    except Exception as e:
        logger.error("lighter_history_failed", symbol=symbol, error=str(e)[:200])
        return []

_ccxt_pool: Dict[str, ccxt_async.Exchange] = {}
_ccxt_locks: Dict[str, asyncio.Lock] = {}

async def _get_ccxt_exchange(ccxt_id: str) -> ccxt_async.Exchange:
    """Get a CCXT exchange from the global pool — creates once, reuses forever.
    Uses per-exchange lock to prevent duplicate load_markets() during racing requests.
    Markets are loaded from SymbolInventory cache (no per-request load_markets).
    """
    if ccxt_id in _ccxt_pool:
        return _ccxt_pool[ccxt_id]

    if ccxt_id not in _ccxt_locks:
        _ccxt_locks[ccxt_id] = asyncio.Lock()

    async with _ccxt_locks[ccxt_id]:
        if ccxt_id in _ccxt_pool:
            return _ccxt_pool[ccxt_id]

        ex_class = getattr(ccxt_async, ccxt_id)
        ex = ex_class({'options': {'defaultType': 'swap'}, 'timeout': 15000})

        si = get_symbol_inventory()
        cached_markets = si.get_markets(ccxt_id) if si else None
        if cached_markets:
            ex.markets = cached_markets
        else:
            await ex.load_markets()

        _ccxt_pool[ccxt_id] = ex
        logger.info("ccxt_pool_created", exchange=ccxt_id, markets=len(ex.markets))
        return ex


async def warm_ccxt_pool():
    """Background: pre-creates all known CCXT exchange instances in the global pool.
    Independent of symbol_inventory — uses cached markets if available, otherwise
    calls load_markets() (per-exchange 45s timeout). Run at startup via create_task.
    """
    logger.info("pool_warm_started")
    known = {
        'binance', 'bybit', 'okx', 'bitget', 'gateio',
        'kucoin', 'mexc', 'bingx', 'hyperliquid',
    }
    si = get_symbol_inventory()
    if si:
        market_ids = set(si.get_all_markets().keys())
        known |= market_ids

    for ccxt_id in sorted(known):
        try:
            if ccxt_id not in _ccxt_pool:
                await _get_ccxt_exchange(ccxt_id)
                logger.info("pool_warm_ok", exchange=ccxt_id)
        except Exception as e:
            logger.debug("pool_warm_skip", exchange=ccxt_id, error=str(e)[:100])
    logger.info("pool_warm_complete", count=len(_ccxt_pool))


async def _live_fetch(exchange: str, symbol: str, days: int) -> list:
    """Live API fetch for a single exchange/symbol — NO Redis, NO DB, just HTTP calls."""
    ex_id = exchange.lower()

    if ex_id == "coinw":
        return await fetch_coinw_history(symbol, days)

    if ex_id == "asterdex":
        try:
            match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
            if not match:
                return []
            raw_sym = match.group(1).upper() + match.group(2).upper()
            url = f"https://fapi.asterdex.com/fapi/v3/fundingRate?symbol={raw_sym}&limit=500"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list):
                            res = [{
                                "timestamp": datetime.fromtimestamp(d['fundingTime'] / 1000, tz=timezone.utc).isoformat(),
                                "rate": float(d['fundingRate'])
                            } for d in data if d.get('fundingRate') is not None]
                            res.sort(key=lambda x: x['timestamp'])
                            return res
        except Exception as e:
            logger.error("asterdex history failed", error=str(e)[:200])
        return []

    if ex_id == "lighter":
        return await fetch_lighter_history(symbol, days)

    if ex_id == "aden":
        try:
            match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
            if not match:
                return []
            raw_sym = match.group(1).upper() + "_" + match.group(2).upper()
            url = f"https://api.aden.io/api/v1/dex_futures/usdt/funding_rate_history?symbol={raw_sym}&limit=500"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and data:
                            res = [{
                                "timestamp": datetime.fromtimestamp(d["fundingTime"] / 1000, tz=timezone.utc).isoformat(),
                                "rate": float(d["fundingRate"]),
                            } for d in data if d.get("fundingRate") is not None]
                            if res:
                                return sorted(res, key=lambda x: x["timestamp"])
                    # If public endpoint fails, try authenticated path
                    logger.info("aden_public_history_empty_trying_auth", symbol=symbol, status=resp.status)
        except Exception as e:
            logger.error("aden_public_history_failed", error=str(e)[:200])

        try:
            auth_data = await aden_fetch_history(symbol)
            if auth_data:
                return sorted(auth_data, key=lambda x: x["timestamp"])
        except Exception as e:
            logger.error("aden_auth_history_failed", error=str(e)[:200])

        return []

    ccxt_map = {'gate': 'gateio', 'hyperliquid': 'hyperliquid'}
    ccxt_id = ccxt_map.get(ex_id, ex_id)
    if not hasattr(ccxt_async, ccxt_id):
        return []

    ex = await _get_ccxt_exchange(ccxt_id)
    try:
        match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
        base, quote = (match.group(1).upper(), match.group(2).upper()) if match else (symbol.upper(), 'USDT')

        possible_syms = []
        if ccxt_id == 'okx':
            possible_syms = [f"{base}-{quote}-SWAP", f"{base}/{quote}:{quote}"]
        elif ccxt_id == 'binance':
            possible_syms = [f"{base}/{quote}:{quote}", f"{base}{quote}"]
        elif ccxt_id == 'mexc':
            possible_syms = [f"{base}/{quote}:{quote}", f"{base}/{quote}", f"{base}_{quote}"]
        elif ccxt_id == 'hyperliquid':
            alt_quote = 'USDC' if quote == 'USDT' else ('USDT' if quote == 'USDC' else quote)
            possible_syms = [f"{base}/{quote}:{quote}", f"{base}/{alt_quote}:{alt_quote}"]
        else:
            possible_syms = [f"{base}/{quote}:{quote}", f"{base}/{quote}", f"{base}{quote}"]

        ccxt_sym = None
        for s in possible_syms:
            if s in ex.markets:
                ccxt_sym = s
                break

        if not ccxt_sym:
            bases_to_try = [base]
            prefix_m = re.match(r'^(1000|10000|1000000|1000000000)(.+)$', base)
            if prefix_m:
                bases_to_try.append(prefix_m.group(2))
            quotes_to_try = [quote]
            if quote == 'USDT':
                quotes_to_try.append('USDC')
            elif quote == 'USDC':
                quotes_to_try.append('USDT')
            for b in bases_to_try:
                for q in quotes_to_try:
                    for s, mkt in ex.markets.items():
                        if mkt.get('swap') and mkt.get('base') == b and (mkt.get('quote') == q or mkt.get('settle') == q):
                            ccxt_sym = s
                            break
                    if ccxt_sym:
                        break
                if ccxt_sym:
                    break

        if ccxt_sym and ex.has.get('fetchFundingRateHistory'):
            since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
            limit = 1000
            hist = await asyncio.wait_for(
                ex.fetch_funding_rate_history(ccxt_sym, since=since, limit=limit),
                timeout=15
            )

            api_data = []
            for h in hist:
                if h.get('fundingRate') is not None:
                    api_data.append({
                        "timestamp": datetime.fromtimestamp(h['timestamp']/1000, tz=timezone.utc).isoformat(),
                        "rate": float(h['fundingRate'])
                    })
            if api_data:
                return sorted(api_data, key=lambda x: x['timestamp'])

        logger.warning("history fetch result", ex_id=ex_id, symbol=symbol, ccxt_sym=ccxt_sym, found=ccxt_sym in ex.markets if ccxt_sym else False)
    except Exception as e:
        logger.error("history api fetch failed", exchange=exchange, symbol=symbol, error=str(e)[:200])
    return []


@router.get("/rates/history_all/{symbol}")
async def get_aggregated_history(symbol: str, days: int = 7):
    """聚合查詢：Redis cache → 並發 per-exchange 15s internal timeout → 60s 整體 timeout。
    第一次請求 (pool cold) 最慢 60s，後續 <1s (cache hit / pool warm)。
    """
    cache_key = f"history_all:{symbol}:{days}"
    redis = get_redis()

    # 1. Redis cache → instant
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()
    active_exchanges = []
    if collector.latest_rates:
        for exch in collector.exchanges.keys():
            if any(clean_sym in k.upper() for k in collector.latest_rates if exch in k):
                active_exchanges.append(exch)
    if not active_exchanges:
        active_exchanges = list(collector.exchanges.keys())

    sem = asyncio.Semaphore(3)

    async def fetch_one(ex: str):
        async with sem:
            try:
                data = await _live_fetch(ex, symbol, days)
                if not data:
                    db = await get_history_from_db(ex, symbol, days)
                    if db:
                        data = _deduplicate_settlement(db)
                return ex, data
            except asyncio.TimeoutError:
                logger.debug("history_all_timeout", exchange=ex, symbol=symbol)
                return ex, []
            except Exception as e:
                logger.error("history_all_failed", exchange=ex, symbol=symbol, error=str(e)[:100])
                return ex, []

    tasks = [asyncio.create_task(fetch_one(ex)) for ex in active_exchanges]
    done, pending = await asyncio.wait(tasks, timeout=60)
    for t in pending:
        t.cancel()

    result = {}
    status: Dict[str, str] = {}
    for t in done:
        try:
            ex, data = t.result()
            status[ex] = "ok" if data else "empty"
            if data:
                result[ex] = [{"time": int(datetime.fromisoformat(h['timestamp']).timestamp()), "value": h['rate']} for h in data]
        except Exception:
            pass
    for t in pending:
        ex_name = "unknown"
        try:
            coro = t.get_coro()
            if coro and hasattr(coro, 'cr_frame'):
                ex_name = coro.cr_frame.f_locals.get('ex', 'unknown')
        except Exception:
            pass
        status[ex_name] = "timeout"

    response = {"data": result, "status": status}

    if redis:
        try:
            await redis.setex(cache_key, 3600, json.dumps(response))
        except Exception:
            pass

    return response


@router.get("/rates/history/{exchange}/{symbol}")
async def get_historical_rates(exchange: str, symbol: str, days: int = 7):
    """歷史資金費率：Redis cache → DB → live API (15s internal timeout on API call only).
    使用者 99% 請求 <1ms (cache hit)，最慢 30s (第一次 + load_markets)。
    """
    cache_key = f"history:{exchange.lower()}:{symbol.upper()}:{days}"
    redis = get_redis()

    # 1. Redis → return immediately
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # 2. DB → return only if data spans the full requested period
    db_data = await get_history_from_db(exchange, symbol, days)
    if db_data:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        earliest_ts = min(datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")) for d in db_data)
        if earliest_ts <= since:
            return db_data
        logger.info("history_db_incomplete", exchange=exchange, symbol=symbol, days=days,
                    earliest=earliest_ts.isoformat(), since=since.isoformat())

    # 3. Live fetch (internal 15s timeout wraps only fetchFundingRateHistory, not exchange creation)
    try:
        raw = await _live_fetch(exchange, symbol, days)
    except asyncio.TimeoutError:
        logger.warning("history_live_timeout", exchange=exchange, symbol=symbol)
        raw = []

    data = _deduplicate_settlement(raw) if raw else []

    # 4. Fallback: live API 無資料時，使用 DB 已累積的資料
    #    適用於無歷史 API 的交易所 (e.g., lighter)
    if not data and db_data:
        logger.info("history_db_fallback", exchange=exchange, symbol=symbol,
                     days=days, db_points=len(db_data))
        data = _deduplicate_settlement(db_data) or db_data

    if data:
        await _store_history_batch(exchange.lower(), symbol, data)
    if redis:
        try:
            await redis.setex(cache_key, _HISTORY_CACHE_TTL, json.dumps(data))
        except Exception:
            pass

    return data


@router.get("/analysis/spreads")
async def get_funding_spreads():
    latest = collector.latest_rates.values()
    by_symbol = {}
    for item in latest:
        sym = item["symbol"]
        if sym not in by_symbol: by_symbol[sym] = []
        by_symbol[sym].append(item)
    spreads = []
    for sym, rates in by_symbol.items():
        if len(rates) > 1:
            rates_sorted = sorted(rates, key=lambda x: x["rate"])
            spreads.append({
                "symbol": sym, "min_exchange": rates_sorted[0]["exchange"], "min_rate": rates_sorted[0]["rate"],
                "max_exchange": rates_sorted[-1]["exchange"], "max_rate": rates_sorted[-1]["rate"],
                "spread": rates_sorted[-1]["rate"] - rates_sorted[0]["rate"], "timestamp": datetime.now(timezone.utc).isoformat()
            })
    return sorted(spreads, key=lambda x: x["spread"], reverse=True)


@router.get("/analysis/spread-history")
async def get_spread_history(symbol: str = "", hours: int = 48):
    """Return historical spread snapshots for one or all symbols."""
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with SessionLocal() as session:
            from sqlalchemy import select
            stmt = select(SpreadSnapshot).where(SpreadSnapshot.timestamp >= since).order_by(SpreadSnapshot.timestamp)
            if symbol:
                stmt = stmt.where(SpreadSnapshot.symbol == symbol.upper())
            rows = (await session.execute(stmt)).scalars().all()

        # Group by symbol as {symbol: [[timestamp_epoch_ms, spread], ...]}
        result: Dict[str, list] = {}
        for r in rows:
            sym = r.symbol
            if sym not in result:
                result[sym] = []
            ts_ms = int(r.timestamp.replace(tzinfo=timezone.utc).timestamp() * 1000)
            result[sym].append([ts_ms, r.spread])
        return result
    except Exception as e:
        return {"error": str(e)}


def _calc_slippage(levels: list, size: float, is_buy: bool) -> dict:
    """Estimate average fill price and slippage for a market order of `size` units.
    `levels` is a list of [price, quantity, ...] from order book (bids or asks).
    """
    remaining = size
    total_cost = 0.0
    filled = 0
    for level in levels:
        if remaining <= 0:
            break
        price, qty = level[0], level[1]
        take = min(qty, remaining)
        total_cost += take * price
        filled += take
        remaining -= take
    if filled == 0:
        return {"filled": 0, "avg_price": 0, "slippage_pct": 0, "slippage_cost": 0}
    avg_price = total_cost / filled
    best_price = levels[0][0] if levels else 0
    slippage_cost = total_cost - (filled * best_price)
    slippage_pct = (slippage_cost / total_cost) * 100 if total_cost else 0
    return {"filled": filled, "avg_price": round(avg_price, 6), "slippage_pct": round(abs(slippage_pct), 4), "slippage_cost": round(abs(slippage_cost), 2), "remaining": round(remaining, 6)}


@router.get("/orderbook/{exchange}/{symbol}")
async def get_orderbook(exchange: str, symbol: str, limit: int = 20, buy_size: float = 10000, sell_size: float = 10000):
    """Fetch order book + slippage analysis for a given exchange + symbol."""
    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
    if not match:
        return {"error": "invalid symbol"}
    base, quote = match.group(1).upper(), match.group(2).upper()

    ex_id = exchange.lower()
    if ex_id == 'gate': ex_id = 'gateio'
    if ex_id == 'kucoin': limit = max(limit, 20)

    # Normalize symbol to match order book format
    raw_sym = f"{base}{quote}"

    # Aden: use perp-api.aden.io public order book endpoint
    if ex_id == 'aden':
        try:
            ticker_id = f"{base}-PERP{quote}"
            url = f"https://perp-api.aden.io/orderbook?ticker_id={ticker_id}&depth={limit}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        d = await resp.json()
                        bids = d.get('bids', [])
                        asks = d.get('asks', [])
                        best_bid = float(bids[0][0]) if bids else 0
                        best_ask = float(asks[0][0]) if asks else 0
                        spread = ((best_ask - best_bid) / best_bid) * 100 if best_bid else 0
                        return {
                            "exchange": exchange, "symbol": symbol,
                            "best_bid": best_bid, "best_ask": best_ask,
                            "spread_pct": round(spread, 4),
                            "bid_depth": len(bids), "ask_depth": len(asks),
                            "buy_analysis": _calc_slippage(asks, buy_size, True),
                            "sell_analysis": _calc_slippage(bids, sell_size, False),
                            "bids": [[round(float(b[0]), 6), round(float(b[1]), 4)] for b in bids[:10]],
                            "asks": [[round(float(a[0]), 6), round(float(a[1]), 4)] for a in asks[:10]],
                        }
        except Exception as e:
            logger.error("aden orderbook failed", error=str(e)[:200])
            return {"error": f"Aden orderbook: {e}"}

    # CoinW: use CCXT if available, otherwise REST
    if ex_id == 'coinw':
        try:
            cl = ccxt_sync.coinw()
            ob = cl.fetch_order_book(f"{base}/{quote}", limit=limit)
            bids = ob.get('bids', []); asks = ob.get('asks', [])
            best_bid = bids[0][0] if bids else 0; best_ask = asks[0][0] if asks else 0
            spread = ((best_ask - best_bid) / best_bid) * 100 if best_bid else 0
            return {
                "exchange": exchange, "symbol": symbol,
                "best_bid": best_bid, "best_ask": best_ask,
                "spread_pct": round(spread, 4), "bid_depth": len(bids), "ask_depth": len(asks),
                "buy_analysis": _calc_slippage(asks, buy_size, True),
                "sell_analysis": _calc_slippage(bids, sell_size, False),
                "bids": [[round(b[0], 6), round(b[1], 4)] for b in bids[:10]],
                "asks": [[round(a[0], 6), round(a[1], 4)] for a in asks[:10]],
            }
        except Exception as e:
            logger.error("coinw orderbook failed", error=str(e)[:200])
            return {"error": f"CoinW orderbook: {e}"}

    try:
        if hasattr(ccxt_async, ex_id):
            ex_class = getattr(ccxt_async, ex_id)
            ex = ex_class({'options': {'defaultType': 'swap'}, 'timeout': 15000})
            try:
                await ex.load_markets()

                possible_syms = []
                if ex_id == 'okx':
                    possible_syms = [f"{base}-{quote}-SWAP", f"{base}/{quote}:{quote}"]
                elif ex_id == 'binance':
                    possible_syms = [f"{base}/{quote}:{quote}", f"{base}{quote}"]
                elif ex_id == 'mexc':
                    possible_syms = [f"{base}/{quote}:{quote}", f"{base}/{quote}", f"{base}_{quote}"]
                elif ex_id == 'hyperliquid':
                    possible_syms = [f"{base}/{quote}:{quote}"]
                else:
                    possible_syms = [f"{base}/{quote}:{quote}", f"{base}/{quote}", f"{base}{quote}"]

                ccxt_sym = None
                for s in possible_syms:
                    if s in ex.markets:
                        ccxt_sym = s
                        break
                if not ccxt_sym:
                    bases_to_try = [base]
                    prefix_m = re.match(r'^(1000|10000|1000000|1000000000)(.+)$', base)
                    if prefix_m:
                        bases_to_try.append(prefix_m.group(2))
                    for b in bases_to_try:
                        for s, mkt in ex.markets.items():
                            if mkt.get('swap') and mkt.get('base') == b and (mkt.get('quote') == quote or mkt.get('settle') == quote):
                                ccxt_sym = s
                                break
                        if ccxt_sym:
                            break

                if ccxt_sym and ex.has.get('fetchOrderBook'):
                    ob = await ex.fetch_order_book(ccxt_sym, limit=limit)
                    bids = ob.get('bids', [])
                    asks = ob.get('asks', [])
                    best_bid = bids[0][0] if bids else 0
                    best_ask = asks[0][0] if asks else 0
                    spread = ((best_ask - best_bid) / best_bid) * 100 if best_bid else 0

                    return {
                        "exchange": exchange,
                        "symbol": symbol,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "spread_pct": round(spread, 4),
                        "bid_depth": len(bids),
                        "ask_depth": len(asks),
                        "buy_analysis": _calc_slippage(asks, buy_size, True),
                        "sell_analysis": _calc_slippage(bids, sell_size, False),
                        "bids": [[round(b[0], 6), round(b[1], 4)] for b in bids[:10]],
                        "asks": [[round(a[0], 6), round(a[1], 4)] for a in asks[:10]],
                    }
            finally:
                await ex.close()
    except Exception as e:
        logger.error("orderbook fetch failed", exchange=exchange, symbol=symbol, error=str(e)[:200])
        return {"error": str(e)}

    return {"error": "unsupported exchange"}

@router.get("/symbols")
async def get_all_symbols():
    si = get_symbol_inventory()
    if si and si.ready:
        return si.get_all()
    return {}


@router.get("/symbols/{exchange}")
async def get_exchange_symbols(exchange: str):
    si = get_symbol_inventory()
    if si and si.ready:
        return si.get_exchange_symbols(exchange)
    return []


@router.get("/symbols/check/{exchange}/{symbol}")
async def check_symbol_supported(exchange: str, symbol: str):
    si = get_symbol_inventory()
    if si and si.ready:
        return {"supported": si.has_symbol(exchange, symbol)}
    return {"supported": True}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        redis = get_redis()
        if redis:
            keys = await redis.keys("latest:*")
            if keys:
                rates_json = await redis.mget(keys)
                for r in rates_json:
                    if r: await websocket.send_text(r)
        while True: await websocket.receive_text()
    except WebSocketDisconnect: ws_manager.disconnect(websocket)
