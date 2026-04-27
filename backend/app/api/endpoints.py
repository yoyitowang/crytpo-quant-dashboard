from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from backend.app.db.session import get_db
from backend.app.services.collector import collector
from backend.app.services.websocket_manager import ws_manager
from backend.app.models.funding_rate import FundingRate
from typing import List
import logging
import json
from datetime import datetime, timedelta

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/rates/latest")
async def get_latest_rates():
    """Fetch latest rates from Redis for maximum speed."""
    try:
        from backend.app.main import redis
        if redis is None:
            return []
            
        keys = await redis.keys("latest:*")
        if not keys:
            return []
            
        rates_json = await redis.mget(keys)
        rates = [json.loads(r) for r in rates_json if r]
        return rates
    except Exception as e:
        logger.error(f"Error fetching latest rates: {e}")
        return []

@router.get("/analysis/aggregated")
async def get_aggregated_rates(
    days: int = 1, 
    db: AsyncSession = Depends(get_db)
):
    """Calculate average funding rates over a specific period (days)."""
    start_time = datetime.utcnow() - timedelta(days=days)
    
    query = select(
        FundingRate.exchange,
        FundingRate.symbol,
        func.avg(FundingRate.rate).label("avg_rate"),
        func.max(FundingRate.timestamp).label("last_update")
    ).where(
        FundingRate.timestamp >= start_time
    ).group_by(
        FundingRate.exchange, FundingRate.symbol
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        {
            "exchange": r.exchange,
            "symbol": r.symbol,
            "rate": float(r.avg_rate),
            "timestamp": r.last_update.isoformat()
        } for r in rows
    ]

@router.get("/rates/history/{exchange}/{symbol}")
async def get_historical_rates(
    exchange: str, 
    symbol: str, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db)
):
    query = select(FundingRate).where(
        FundingRate.exchange == exchange,
        FundingRate.symbol == symbol
    ).order_by(desc(FundingRate.timestamp)).limit(limit)
    
    result = await db.execute(query)
    rates = result.scalars().all()
    
    # Manually serialize to avoid DateTime JSON errors
    return [
        {
            "exchange": r.exchange,
            "symbol": r.symbol,
            "rate": r.rate,
            "settlement_time": r.settlement_time.isoformat() if r.settlement_time else None,
            "timestamp": r.timestamp.isoformat() if r.timestamp else datetime.utcnow().isoformat()
        } for r in rates
    ]

@router.get("/analysis/spreads")
async def get_funding_spreads():
    """Calculate spreads (diff between max and min funding) for same symbols across exchanges."""
    latest = collector.latest_rates.values()
    by_symbol = {}
    
    for item in latest:
        sym = item["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(item)
    
    spreads = []
    for sym, rates in by_symbol.items():
        if len(rates) > 1:
            rates_sorted = sorted(rates, key=lambda x: x["rate"])
            min_rate = rates_sorted[0]
            max_rate = rates_sorted[-1]
            spreads.append({
                "symbol": sym,
                "min_exchange": min_rate["exchange"],
                "min_rate": min_rate["rate"],
                "max_exchange": max_rate["exchange"],
                "max_rate": max_rate["rate"],
                "spread": max_rate["rate"] - min_rate["rate"],
                "timestamp": datetime.utcnow().isoformat()
            })
    
    return sorted(spreads, key=lambda x: x["spread"], reverse=True)

@router.get("/analysis/summary")
async def get_market_summary():
    """Get high-level market summary statistics."""
    try:
        from backend.app.main import redis
        if redis is None: return {}
        
        keys = await redis.keys("latest:*")
        if not keys: return {}
        
        rates_json = await redis.mget(keys)
        all_rates = [json.loads(r) for r in rates_json if r]
        
        if not all_rates: return {}
        
        # 1. 市場平均費率
        avg_rate = sum(r['rate'] for r in all_rates) / len(all_rates)
        
        # 2. 排序獲取極端值
        sorted_rates = sorted(all_rates, key=lambda x: x['rate'])
        top_neg = sorted_rates[:3]
        top_pos = sorted_rates[-3:][::-1]
        
        # 3. 穩定幣分布
        usdt_rates = [r['rate'] for r in all_rates if 'USDT' in r['symbol']]
        usdc_rates = [r['rate'] for r in all_rates if 'USDC' in r['symbol']]
        
        avg_usdt = sum(usdt_rates) / len(usdt_rates) if usdt_rates else 0
        avg_usdc = sum(usdc_rates) / len(usdc_rates) if usdc_rates else 0
        
        return {
            "market_sentiment": "Bullish" if avg_rate > 0 else "Bearish",
            "avg_funding_rate": avg_rate,
            "top_positive": top_pos,
            "top_negative": top_neg,
            "stablecoin_stats": {
                "usdt_avg": avg_usdt,
                "usdc_avg": avg_usdc
            },
            "total_symbols": len(all_rates)
        }
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return {}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send current latest rates upon connection
        from backend.app.main import redis
        if redis:
            keys = await redis.keys("latest:*")
            if keys:
                rates_json = await redis.mget(keys)
                for r in rates_json:
                    if r: await websocket.send_text(r)
            
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
