"""Historical funding rate backfill for exchanges with history endpoints.

Usage:
    python -m backend.app.backfill --exchanges binance,bybit --days 90
    python -m backend.app.backfill --all --days 30
    python -m backend.app.backfill --dry-run --exchanges binance --days 7
"""

import asyncio
import argparse
import structlog
import aiohttp
import math
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from backend.app.db.session import SessionLocal
from backend.app.models.funding_rate import FundingRate
from backend.app.services.collector import interval_manager
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

logger = structlog.get_logger()

SUPPORTED_EXCHANGES = ["binance", "bybit", "okx", "gate", "mexc", "bingx"]
MAX_CONCURRENT_SYMBOLS = 5
REQUEST_DELAY = 0.5


class Backfiller:
    def __init__(self, days: int = 30, dry_run: bool = False, symbols: Optional[List[str]] = None):
        self.days = days
        self.dry_run = dry_run
        self.symbols = symbols
        self.total = 0
        self.end_time = datetime.now(timezone.utc)
        self.start_time = self.end_time - timedelta(days=days)

    async def run(self, exchanges: List[str]):
        await interval_manager.refresh()
        sem = asyncio.Semaphore(2)
        tasks = [self._backfill_exchange(ex, sem) for ex in exchanges]
        await asyncio.gather(*tasks)
        logger.info("backfill_complete", total_rows=self.total)

    async def _backfill_exchange(self, exchange: str, sem: asyncio.Semaphore):
        async with sem:
            logger.info("backfill_start", exchange=exchange, days=self.days)

            symbols = await self._fetch_symbols(exchange)
            if self.symbols:
                symbols = [s for s in symbols if s in self.symbols]
            logger.info("backfill_symbols", exchange=exchange, count=len(symbols))

            async with SessionLocal() as session:
                symbol_sem = asyncio.Semaphore(MAX_CONCURRENT_SYMBOLS)

                async def process_symbol(sym: str):
                    async with symbol_sem:
                        rows = await self._fetch_and_convert(exchange, sym)
                        if rows and not self.dry_run:
                            await self._upsert_batch(session, rows)
                        self.total += len(rows)
                        logger.info("backfill_symbol_done", exchange=exchange, symbol=sym, rows=len(rows))

                await asyncio.gather(*[process_symbol(s) for s in symbols])

            logger.info("backfill_exchange_done", exchange=exchange, total_rows=self.total)

    async def _fetch_symbols(self, exchange: str) -> List[str]:
        async with aiohttp.ClientSession() as s:
            if exchange == "binance":
                async with s.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=15) as r:
                    data = await r.json()
                    return [x["symbol"] for x in data["symbols"]
                            if x["status"] == "TRADING" and x.get("contractType") == "PERPETUAL"]
            elif exchange == "bybit":
                async with s.get("https://api.bybit.com/v5/market/instruments-info?category=linear&status=Trading&limit=1000", timeout=15) as r:
                    data = await r.json()
                    return [i["symbol"] for i in data["result"]["list"] if i["symbol"].endswith("USDT")]
            elif exchange == "okx":
                async with s.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP&limit=500", timeout=15) as r:
                    data = await r.json()
                    return [i["instId"] for i in data["data"] if i["settleCcy"] == "USDT" and i.get("state") == "live"]
            elif exchange == "gate":
                async with s.get("https://api.gateio.ws/api/v4/futures/usdt/contracts", timeout=15) as r:
                    data = await r.json()
                    return [c["name"] for c in data]
            elif exchange == "mexc":
                async with s.get("https://contract.mexc.com/api/v1/contract/detail", timeout=15) as r:
                    data = await r.json()
                    if isinstance(data.get("data"), list):
                        return [d["symbol"] for d in data["data"] if d.get("quoteCoin") == "USDT"]
                    return []
            elif exchange == "bingx":
                async with s.get("https://open-api.bingx.com/openApi/swap/v2/quote/contracts", timeout=15) as r:
                    data = await r.json()
                    contracts = data.get("data", [])
                    return [c["symbol"] for c in contracts if c["symbol"].endswith("USDT")]
            return []

    async def _fetch_and_convert(self, exchange: str, symbol: str) -> List[Dict[str, Any]]:
        start_ms = int(self.start_time.timestamp() * 1000)
        end_ms = int(self.end_time.timestamp() * 1000)

        items = []
        if exchange == "binance":
            items = await self._fetch_binance(symbol, start_ms, end_ms)
        elif exchange == "bybit":
            items = await self._fetch_bybit(symbol, start_ms, end_ms)
        elif exchange == "okx":
            items = await self._fetch_okx(symbol, start_ms, end_ms)
        elif exchange == "gate":
            items = await self._fetch_gate(symbol, start_ms, end_ms)
        elif exchange == "mexc":
            items = await self._fetch_mexc(symbol, start_ms, end_ms)
        elif exchange == "bingx":
            items = await self._fetch_bingx(symbol, start_ms, end_ms)
        return self._to_db_rows(exchange, symbol, items)

    def _to_db_rows(self, exchange: str, symbol: str, items: List[Dict]) -> List[Dict]:
        rows = []
        for item in items:
            rate = item.get("rate")
            if rate is None:
                continue
            funding_time = item.get("funding_time")
            if funding_time is None:
                continue
            interval = item.get("interval") or interval_manager.get(exchange, symbol)
            settlement = item.get("settlement_time")
            if settlement is None and interval:
                settlement = funding_time + timedelta(hours=interval)
            rows.append({
                "exchange": exchange,
                "symbol": symbol.upper().replace("-", "").replace("_", ""),
                "timestamp": funding_time,
                "rate": float(rate),
                "funding_interval": interval,
                "settlement_time": settlement,
            })
        return rows

    async def _upsert_batch(self, session, rows: List[Dict]):
        stmt = pg_insert(FundingRate).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="funding_rates_pkey",
            set_={
                "rate": stmt.excluded.rate,
                "funding_interval": stmt.excluded.funding_interval,
                "settlement_time": stmt.excluded.settlement_time,
            },
        )
        await session.execute(stmt)
        await session.commit()

    async def _fetch_binance(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        await asyncio.sleep(REQUEST_DELAY)
        rows = []
        max_pages = 10
        async with aiohttp.ClientSession() as s:
            while start_ms < end_ms and max_pages > 0:
                max_pages -= 1
                params = {"symbol": symbol, "startTime": start_ms, "endTime": end_ms, "limit": 1000}
                try:
                    async with s.get("https://fapi.binance.com/fapi/v1/fundingRate", params=params, timeout=15) as r:
                        if r.status == 429:
                            await asyncio.sleep(5)
                            continue
                        if r.status != 200:
                            break
                        data = await r.json()
                        if not data:
                            break
                        for item in data:
                            ft = datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc)
                            rows.append({
                                "rate": item["fundingRate"],
                                "funding_time": ft,
                                "settlement_time": ft + timedelta(hours=8),
                                "interval": 8,
                            })
                        start_ms = data[-1]["fundingTime"] + 1
                except Exception as e:
                    logger.warning("binance_fetch_error", symbol=symbol, error=str(e)[:100])
                    break
        return rows

    async def _fetch_bybit(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        await asyncio.sleep(REQUEST_DELAY)
        rows = []
        cursor = None
        max_pages = 200
        async with aiohttp.ClientSession() as s:
            while max_pages > 0:
                max_pages -= 1
                params = {"category": "linear", "symbol": symbol, "limit": 200}
                if cursor:
                    params["cursor"] = cursor
                try:
                    async with s.get("https://api.bybit.com/v5/market/funding/history", params=params, timeout=15) as r:
                        if r.status == 429:
                            await asyncio.sleep(5)
                            continue
                        if r.status != 200:
                            break
                        data = await r.json()
                        items = data.get("result", {}).get("list", [])
                        if not items:
                            break
                        too_old = False
                        for item in items:
                            ts = int(item["fundingRateTimestamp"])
                            if ts < start_ms:
                                too_old = True
                                break
                            if ts > end_ms:
                                continue
                            ft = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            rows.append({
                                "rate": item["fundingRate"],
                                "funding_time": ft,
                                "settlement_time": ft + timedelta(hours=8),
                                "interval": 8,
                            })
                        if too_old:
                            break
                        cursor = data.get("result", {}).get("nextPageCursor")
                        if not cursor:
                            break
                except Exception as e:
                    logger.warning("bybit_fetch_error", symbol=symbol, error=str(e)[:100])
                    break
        return rows

    async def _fetch_okx(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        await asyncio.sleep(REQUEST_DELAY)
        rows = []
        before = None
        max_pages = 200
        async with aiohttp.ClientSession() as s:
            while max_pages > 0:
                max_pages -= 1
                params = {"instId": symbol, "limit": 100}
                if before:
                    params["before"] = before
                try:
                    async with s.get("https://www.okx.com/api/v5/public/funding-rate-history", params=params, timeout=15) as r:
                        if r.status == 429:
                            await asyncio.sleep(5)
                            continue
                        if r.status != 200:
                            break
                        data = await r.json()
                        items = data.get("data", [])
                        if not items:
                            break
                        too_old = False
                        for item in items:
                            ts = int(item["fundingTime"])
                            if ts < start_ms:
                                too_old = True
                                break
                            if ts > end_ms:
                                continue
                            ft = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            rows.append({
                                "rate": item["fundingRate"],
                                "funding_time": ft,
                                "settlement_time": ft + timedelta(hours=8),
                                "interval": 8,
                            })
                        if too_old:
                            break
                        before = items[-1]["fundingTime"]
                except Exception as e:
                    logger.warning("okx_fetch_error", symbol=symbol, error=str(e)[:100])
                    break
        return rows

    async def _fetch_gate(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        await asyncio.sleep(REQUEST_DELAY)
        rows = []
        from_ts = int(start_ms / 1000)
        to_ts = int(end_ms / 1000)
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get("https://api.gateio.ws/api/v4/futures/usdt/funding_rate",
                    params={"contract": symbol, "from": from_ts, "to": to_ts, "limit": 100}, timeout=15) as r:
                    if r.status == 200:
                        data = await r.json()
                        for item in data:
                            ts = item["t"]
                            if ts < from_ts or ts > to_ts:
                                continue
                            ft = datetime.fromtimestamp(ts, tz=timezone.utc)
                            rows.append({
                                "rate": item["r"],
                                "funding_time": ft,
                                "settlement_time": ft + timedelta(hours=8),
                                "interval": 8,
                            })
            except Exception as e:
                logger.warning("gate_fetch_error", symbol=symbol, error=str(e)[:100])
        return rows

    async def _fetch_mexc(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        await asyncio.sleep(REQUEST_DELAY)
        rows = []
        page = 1
        async with aiohttp.ClientSession() as s:
            while True:
                params = {"symbol": symbol, "page_size": 100, "page_no": page}
                try:
                    async with s.get("https://contract.mexc.com/api/v1/contract/funding_rate/history", params=params, timeout=15) as r:
                        if r.status == 429:
                            await asyncio.sleep(5)
                            continue
                        if r.status != 200:
                            break
                        data = await r.json()
                        items = data.get("data", {}).get("resultList", [])
                        if not items:
                            break
                        for item in items:
                            ts = int(item["settleTime"])
                            if ts < start_ms:
                                return rows
                            if ts > end_ms:
                                continue
                            ft = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            rows.append({
                                "rate": item["fundingRate"],
                                "funding_time": ft,
                                "settlement_time": ft + timedelta(hours=item.get("collectCycle", 8)),
                                "interval": item.get("collectCycle", 8),
                            })
                        page += 1
                except Exception as e:
                    logger.warning("mexc_fetch_error", symbol=symbol, error=str(e)[:100])
                    break
        return rows

    async def _fetch_bingx(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        await asyncio.sleep(REQUEST_DELAY)
        rows = []
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get("https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate", params={"symbol": symbol}, timeout=15) as r:
                    if r.status != 200:
                        return rows
                    data = await r.json()
                    items = data.get("data", [])
                    if not items:
                        return rows
                    for item in items:
                        ts = int(item["fundingTime"])
                        if ts < start_ms or ts > end_ms:
                            continue
                        ft = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                        rows.append({
                            "rate": item["fundingRate"],
                            "funding_time": ft,
                            "settlement_time": ft + timedelta(hours=8),
                            "interval": 8,
                        })
            except Exception as e:
                logger.warning("bingx_fetch_error", symbol=symbol, error=str(e)[:100])
        return rows


async def main():
    parser = argparse.ArgumentParser(description="Backfill historical funding rates")
    parser.add_argument("--exchanges", type=str, help="Comma-separated list of exchanges")
    parser.add_argument("--all", action="store_true", help="Backfill all supported exchanges")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backfill (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch data but don't write to DB")
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols to backfill")
    args = parser.parse_args()

    if args.all:
        exchanges = SUPPORTED_EXCHANGES
    elif args.exchanges:
        exchanges = [e.strip().lower() for e in args.exchanges.split(",")]
    else:
        parser.print_help()
        return

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    for ex in exchanges:
        if ex not in SUPPORTED_EXCHANGES:
            logger.warning("unsupported_exchange", exchange=ex, supported=SUPPORTED_EXCHANGES)
            return

    backfiller = Backfiller(days=args.days, dry_run=args.dry_run, symbols=symbols)
    await backfiller.run(exchanges)


if __name__ == "__main__":
    asyncio.run(main())
