from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Response
from backend.app.services.collector import collector
from backend.app.services.websocket_manager import ws_manager
from backend.app.db.session import SessionLocal
from backend.app.models.funding_rate import FundingRate
from typing import List
import structlog
import json
import re
import asyncio
from datetime import datetime, timedelta, timezone
import ccxt.async_support as ccxt_async
from sqlalchemy import select, desc

router = APIRouter()
logger = structlog.get_logger()

async def get_history_from_db(exchange: str, symbol: str, days: int) -> list:
    """Query funding rate history from local PostgreSQL (fast, no external API)."""
    clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()
    since = datetime.utcnow() - timedelta(days=days)
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
                return [{"timestamp": r.timestamp.isoformat(), "rate": r.rate} for r in rows]
    except Exception as e:
        logger.debug("db read unavailable", exchange=exchange, symbol=symbol)
    return []

@router.get("/rates/compressed")
async def get_compressed_rates():
    """極簡版數據介面，專供前端快速渲染矩陣使用，移除不必要的欄位與冗餘計算。"""
    try:
        from backend.app.main import redis
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
    from backend.app.main import redis
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
    status_code = 200 if not issues else 503
    return Response(
        status_code=status_code,
        content=json.dumps({
            "status": "ok" if not issues else "degraded",
            "issues": issues,
            "last_update": latest_ts,
            "active_exchanges": list(collector.exchanges.keys()),
            "symbols_tracked": len(collector.latest_rates)
        }),
        media_type="application/json"
    )

@router.get("/rates/latest")
async def get_latest_rates():
    try:
        from backend.app.main import redis
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
        from backend.app.main import redis
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
    """專屬 CoinW 歷史 API 抓取邏輯"""
    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
    base = match.group(1).lower() if match else symbol.lower()
    
    url = "https://futuresapi.faefrdpenn.com/v1/futuresc/public/selectFundingRateHistory"
    payload = {"instrument": base, "day": days}
    headers = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 0:
                        return [
                            {
                                "timestamp": datetime.strptime(item['createdDate'], "%Y-%m-%d %H:%M").isoformat(),
                                "rate": float(item['fundingRate'])
                            } for item in data['data']
                        ]
    except Exception as e:
        logger.error("coinw history api error", error=str(e)[:200])
    return []

@router.get("/rates/history_all/{symbol}")
async def get_aggregated_history(symbol: str, days: int = 7):
    """聚合查詢：並發向所有交易所請求該幣種的歷史，不再依賴本地資料庫。加入 Redis 快取。
    
    只查詢在即時資料中有該幣種的交易所，避免無謂的 API 請求。
    Returns per-exchange data with status: {"data": {...}, "status": {"binance": "ok", ...}}
    Each exchange has a 15s timeout. Results returned as soon as all complete or timeout.
    """
    cache_key = f"history_all:{symbol}:{days}"
    try:
        from backend.app.main import redis
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
    except Exception as e:
        logger.error("redis read error (history_all)", error=str(e)[:200])

    clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()
    active_exchanges = []
    for exch in collector.exchanges.keys():
        if any(clean_sym in k.upper() for k in collector.latest_rates if exch in k):
            active_exchanges.append(exch)

    async def fetch_with_name(exchange: str) -> tuple[str, list]:
        try:
            data = await asyncio.wait_for(
                get_historical_rates(exchange, symbol, days),
                timeout=15
            )
            return exchange, data
        except asyncio.TimeoutError:
            logger.warning("history timeout", exchange=exchange, symbol=symbol)
            return exchange, []
        except Exception as e:
            logger.error("history failed", exchange=exchange, symbol=symbol, error=str(e)[:200])
            return exchange, []

    tasks = [fetch_with_name(ex) for ex in active_exchanges]
    results = await asyncio.gather(*tasks)

    result = {}
    status: dict[str, str] = {}
    for ex, history in results:
        status[ex] = "ok" if history else "empty"
        if history:
            result[ex] = [{"time": int(datetime.fromisoformat(h['timestamp']).timestamp()), "value": h['rate']} for h in history]

    response = {"data": result, "status": status}

    try:
        if redis and result:
            await redis.setex(cache_key, 900, json.dumps(response))
    except Exception as e:
        logger.error("redis write error (history_all)", error=str(e)[:200])

    return response

@router.get("/rates/history/{exchange}/{symbol}")
async def get_historical_rates(exchange: str, symbol: str, days: int = 7):
    """獲取單一交易所歷史資料：全面改為即時 API 抓取，加入 Redis 快取保護。"""
    cache_key = f"history:{exchange.lower()}:{symbol.upper()}:{days}"
    try:
        from backend.app.main import redis
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
    except Exception as e:
        logger.error("redis read error (history)", error=str(e)[:200])

    if exchange.lower() == "coinw":
        res = await fetch_coinw_history(symbol, days)
        try:
            if redis and res:
                await redis.setex(cache_key, 900, json.dumps(res))
        except: pass
        return res

    if exchange.lower() == "asterdex":
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
                            if redis and res:
                                await redis.setex(cache_key, 900, json.dumps(res))
                            return res
        except Exception as e:
            logger.error("asterdex history failed", error=str(e)[:200])
        return []

    if exchange.lower() == "lighter":
        return []

    # DB has the best data (accumulated from collectors) — check first
    db_hist = await get_history_from_db(exchange, symbol, days)
    if db_hist:
        try:
            from backend.app.main import redis
            if redis:
                await redis.setex(cache_key, 900, json.dumps(db_hist))
        except: pass
        return db_hist

    # For Aden: try authenticated API if credentials are configured
    if exchange.lower() == "aden":
        from backend.app.core.config import settings
        if settings.aden_auth_available:
            from backend.app.services.aden_api import init, fetch_funding_rate_history
            priv_key = settings.ADEN_API_PRIVATE_KEY.get_secret_value() if settings.ADEN_API_PRIVATE_KEY else ""
            init(settings.ADEN_API_USER, settings.ADEN_API_SIGNER, priv_key)
            res = await fetch_funding_rate_history(symbol, limit=500)
            if res:
                res.sort(key=lambda x: x['timestamp'])
                try:
                    from backend.app.main import redis
                    if redis:
                        await redis.setex(cache_key, 900, json.dumps(res))
                except: pass
                return res
        # No auth configured or API failed — DB will accumulate over time
        return []

    try:
        ex_id = exchange.lower()
        if ex_id == 'gate': ex_id = 'gateio'
        if ex_id == 'hyperliquid': ex_id = 'hyperliquid'

        if hasattr(ccxt_async, ex_id):
            ex_class = getattr(ccxt_async, ex_id)
            ex = ex_class({'options': {'defaultType': 'swap'}, 'timeout': 15000})
            try:
                match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
                base, quote = (match.group(1).upper(), match.group(2).upper()) if match else (symbol.upper(), 'USDT')

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
                    for s, m in ex.markets.items():
                        if m.get('swap') and m.get('base') == base and (m.get('quote') == quote or m.get('settle') == quote):
                            ccxt_sym = s
                            break

                if ccxt_sym and ex.has.get('fetchFundingRateHistory'):
                    since = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
                    limit = 1000
                    hist = await ex.fetch_funding_rate_history(ccxt_sym, since=since, limit=limit)

                    api_data = []
                    for h in hist:
                        if h.get('fundingRate') is not None:
                            api_data.append({
                                "timestamp": datetime.fromtimestamp(h['timestamp']/1000, tz=timezone.utc).isoformat(),
                                "rate": float(h['fundingRate'])
                            })

                    if api_data:
                        res = sorted(api_data, key=lambda x: x['timestamp'])
                        try:
                            if redis: await redis.setex(cache_key, 900, json.dumps(res))
                        except: pass
                        return res

                logger.warning("history fetch result", ex_id=ex_id, symbol=symbol, ccxt_sym=ccxt_sym, found=ccxt_sym in ex.markets if ccxt_sym else False)
            finally:
                await ex.close()
    except Exception as e:
        logger.error("history api fetch failed", exchange=exchange, symbol=symbol, error=str(e)[:200])

    return []

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
                "spread": rates_sorted[-1]["rate"] - rates_sorted[0]["rate"], "timestamp": datetime.utcnow().isoformat()
            })
    return sorted(spreads, key=lambda x: x["spread"], reverse=True)


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
                    for s, m in ex.markets.items():
                        if m.get('swap') and m.get('base') == base and (m.get('quote') == quote or m.get('settle') == quote):
                            ccxt_sym = s
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

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        from backend.app.main import redis
        if redis:
            keys = await redis.keys("latest:*")
            if keys:
                rates_json = await redis.mget(keys)
                for r in rates_json:
                    if r: await websocket.send_text(r)
        while True: await websocket.receive_text()
    except WebSocketDisconnect: ws_manager.disconnect(websocket)
