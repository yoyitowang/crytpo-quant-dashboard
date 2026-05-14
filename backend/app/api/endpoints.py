from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.services.collector import collector
from backend.app.services.websocket_manager import ws_manager
from typing import List
import logging
import json
import re
import asyncio
from datetime import datetime, timedelta
import ccxt.async_support as ccxt_async

router = APIRouter()
logger = logging.getLogger(__name__)

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
        logger.error(f"Compressed Rates Error: {e}")
        return []

@router.get("/health")
async def health_check():
    latest_ts = "None"
    if collector.latest_rates:
        ts_list = [r['timestamp'] for r in collector.latest_rates.values() if isinstance(r.get('timestamp'), datetime)]
        if ts_list:
            latest_ts = max(ts_list).isoformat()
            
    return {
        "status": "ok",
        "last_update": latest_ts,
        "active_exchanges": list(collector.exchanges.keys()),
        "symbols_tracked": len(collector.latest_rates)
    }

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
        logger.error(f"Error fetching latest: {e}")
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
        logger.error(f"Summary Error: {e}")
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
        logger.error(f"CoinW History API Error: {e}")
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
        logger.error(f"Redis Read Error (history_all): {e}")

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
            logger.warning(f"History timeout: {exchange}/{symbol}")
            return exchange, []
        except Exception as e:
            logger.error(f"History failed: {exchange}/{symbol}: {e}")
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
        logger.error(f"Redis Write Error (history_all): {e}")

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
        logger.error(f"Redis Read Error (history): {e}")

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
                                "timestamp": datetime.fromtimestamp(d['fundingTime'] / 1000).isoformat(),
                                "rate": float(d['fundingRate'])
                            } for d in data if d.get('fundingRate') is not None]
                            res.sort(key=lambda x: x['timestamp'])
                            if redis and res:
                                await redis.setex(cache_key, 900, json.dumps(res))
                            return res
        except Exception as e:
            logger.error(f"AsterDEX history failed: {e}")
        return []

    if exchange.lower() in ("aden", "lighter"):
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
                                "timestamp": datetime.fromtimestamp(h['timestamp']/1000).isoformat(),
                                "rate": float(h['fundingRate'])
                            })

                    if api_data:
                        res = sorted(api_data, key=lambda x: x['timestamp'])
                        try:
                            if redis: await redis.setex(cache_key, 900, json.dumps(res))
                        except: pass
                        return res

                logger.warning(f"History Fetch: {ex_id} ({symbol}) -> CCXT Sym: {ccxt_sym} | Found: {ccxt_sym in ex.markets if ccxt_sym else False}")
            finally:
                await ex.close()
    except Exception as e:
        logger.error(f"History API fetch failed for {exchange} ({symbol}): {e}")

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
