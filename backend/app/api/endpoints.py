from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, text
from backend.app.db.session import get_db
from backend.app.services.collector import collector
from backend.app.services.websocket_manager import ws_manager
from backend.app.models.funding_rate import FundingRate
from typing import List
import logging
import json
import re
from datetime import datetime, timedelta
import ccxt.async_support as ccxt_async

router = APIRouter()
logger = logging.getLogger(__name__)

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
        
        avg_rate = sum(r['rate'] for r in all_rates) / len(all_rates)
        sorted_rates = sorted(all_rates, key=lambda x: x['rate'])
        top_neg = sorted_rates[:5]
        top_pos = sorted_rates[-5:][::-1]
        
        usdt_rates = [r['rate'] for r in all_rates if 'USDT' in r['symbol']]
        usdc_rates = [r['rate'] for r in all_rates if 'USDC' in r['symbol']]
        avg_usdt = sum(usdt_rates) / len(usdt_rates) if usdt_rates else 0
        avg_usdc = sum(usdc_rates) / len(usdc_rates) if usdc_rates else 0
        
        return {
            "market_sentiment": "Bullish" if avg_rate > 0 else "Bearish",
            "avg_funding_rate": avg_rate,
            "top_positive": top_pos,
            "top_negative": top_neg,
            "stablecoin_stats": { "usdt_avg": avg_usdt, "usdc_avg": avg_usdc },
            "total_symbols": len(all_rates)
        }
    except Exception as e:
        return {}

@router.get("/rates/history_all/{symbol}")
async def get_aggregated_history(
    symbol: str, days: int = 7, db: AsyncSession = Depends(get_db)
):
    """聚合查詢：獲取該幣種在所有交易所的歷史，用於 Modal 比對。"""
    start_time = datetime.utcnow() - timedelta(days=days)
    
    # 使用資料庫查詢所有相關交易所的歷史
    trunc_func = func.date_trunc('hour', FundingRate.timestamp)
    query = select(
        FundingRate.exchange,
        trunc_func.label('ts'),
        func.avg(FundingRate.rate).label('rate')
    ).where(
        FundingRate.symbol == symbol, 
        FundingRate.timestamp >= start_time
    ).group_by(FundingRate.exchange, trunc_func).order_by(trunc_func.asc())
    
    res = await db.execute(query)
    rows = res.all()
    
    # 格式化為前端易用的結構：{ "binance": [...], "okx": [...] }
    result = {}
    for r in rows:
        ex = r.exchange
        if ex not in result: result[ex] = []
        result[ex].append({"time": int(r.ts.timestamp()), "value": float(r.rate)})
        
    return result

@router.get("/rates/history/{exchange}/{symbol}")
async def get_historical_rates(
    exchange: str, symbol: str, days: int = 7, db: AsyncSession = Depends(get_db)
):
    """獲取單一交易所歷史資料：先查 DB，若無資料則向交易所 API 請求。"""
    start_time = datetime.utcnow() - timedelta(days=days)
    
    trunc_func = func.date_trunc('hour', FundingRate.timestamp)
    query_agg = select(
        trunc_func.label('ts'),
        func.avg(FundingRate.rate).label('rate')
    ).where(
        FundingRate.exchange == exchange, FundingRate.symbol == symbol, FundingRate.timestamp >= start_time
    ).group_by(trunc_func).order_by(trunc_func.asc())
    
    res_agg = await db.execute(query_agg)
    db_data = [{"timestamp": r.ts.isoformat(), "rate": float(r.rate)} for r in res_agg.all()]

    if len(db_data) < 5:
        try:
            ex_id = exchange.lower()
            if hasattr(ccxt_async, ex_id):
                ex_class = getattr(ccxt_async, ex_id)()
                if ex_class.has.get('fetchFundingRateHistory'):
                    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
                    ccxt_sym = f"{match.group(1)}/{match.group(2)}" if match else symbol
                    
                    hist = await ex_class.fetch_funding_rate_history(ccxt_sym, since=int(start_time.timestamp()*1000))
                    api_data = [{"timestamp": datetime.fromtimestamp(h['timestamp']/1000).isoformat(), "rate": h['fundingRate']} for h in hist]
                    await ex_class.close()
                    return sorted(api_data, key=lambda x: x['timestamp'])
                await ex_class.close()
        except Exception as e:
            logger.warning(f"Fallback history fetch failed for {exchange}: {e}")
            
    return sorted(db_data, key=lambda x: x['timestamp'])

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
