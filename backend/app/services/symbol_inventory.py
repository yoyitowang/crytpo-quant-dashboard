import asyncio
import re
import structlog
import aiohttp
import ccxt.async_support as ccxt_async
from typing import Dict, List, Set, Optional

logger = structlog.get_logger()

CCXT_EXCHANGES = ["binance", "bybit", "okx", "bitget", "gateio", "kucoin", "mexc", "bingx", "hyperliquid", "lighter"]

EXCHANGE_NAME_MAP = {
    "binance": "binance", "bybit": "bybit", "okx": "okx",
    "bitget": "bitget", "gate": "gateio", "gateio": "gateio",
    "kucoin": "kucoin", "mexc": "mexc", "bingx": "bingx",
    "hyperliquid": "hyperliquid", "lighter": "lighter",
    "coinw": "coinw", "asterdex": "asterdex", "aden": "aden",
}

FRONTEND_NAME_MAP = {
    "binance": "binance", "bybit": "bybit", "okx": "okx",
    "bitget": "bitget", "gateio": "gate",
    "kucoin": "kucoin", "mexc": "mexc", "bingx": "bingx",
    "hyperliquid": "hyperliquid", "lighter": "lighter",
    "coinw": "coinw", "asterdex": "asterdex", "aden": "aden",
}

def normalize_symbol(symbol: str) -> str:
    return re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()


class SymbolInventory:
    def __init__(self):
        self.symbols: Dict[str, Set[str]] = {}
        self.markets: Dict[str, dict] = {}
        self.lock = asyncio.Lock()
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def refresh(self):
        logger.info("symbol_inventory_refresh_entered")
        async with self.lock:
            self.symbols.clear()
            self.markets.clear()
            self._ready = False
            sem = asyncio.Semaphore(3)

            async def load_ccxt(ex_id: str):
                async with sem:
                    try:
                        logger.info("symbol_inventory_starting", exchange=ex_id)
                        ex_class = getattr(ccxt_async, ex_id)
                        ex = ex_class({"timeout": 20000})
                        try:
                            markets = await asyncio.wait_for(
                                ex.load_markets(), timeout=45
                            )
                            self.markets[ex_id] = markets
                            swaps = {
                                s for s, m in markets.items() if m.get("swap")
                            }
                            clean: Set[str] = set()
                            for s in swaps:
                                clean.add(normalize_symbol(s))
                            self.symbols[ex_id] = clean
                            logger.info(
                                "symbol_inventory_loaded",
                                exchange=ex_id,
                                perpetual_count=len(swaps),
                            )
                        finally:
                            await ex.close()
                    except asyncio.TimeoutError:
                        logger.warning(
                            "symbol_inventory_ccxt_timeout", exchange=ex_id
                        )
                    except Exception as e:
                        err = str(e)[:200] or type(e).__name__
                        logger.error(
                            "symbol_inventory_ccxt_failed",
                            exchange=ex_id,
                            error=err,
                        )

            tasks = [asyncio.create_task(load_ccxt(e)) for e in CCXT_EXCHANGES]
            done, pending = await asyncio.wait(tasks, timeout=180)
            for t in pending:
                t.cancel()
                ex = "unknown"
                try:
                    ex = t.get_coro().cr_frame.f_locals.get("ex_id", "unknown")
                except Exception:
                    pass
                logger.warning("symbol_inventory_task_cancelled", exchange=ex)
            if pending:
                logger.warning(
                    "symbol_inventory_some_timed_out",
                    total=len(tasks),
                    remaining=len(pending),
                )

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.coinw.com/v1/perpum/instruments", timeout=15
                    ) as resp:
                        data = await resp.json()
                        if data.get("code") == 0:
                            coinw_syms = {
                                f"{i['base'].upper()}USDT"
                                for i in data["data"]
                                if i.get("status") == "online"
                            }
                            self.symbols["coinw"] = coinw_syms
                            logger.info(
                                "symbol_inventory_loaded",
                                exchange="coinw",
                                count=len(coinw_syms),
                            )
            except Exception as e:
                logger.error(
                    "coinw_symbol_inventory_failed", error=str(e)[:200]
                )

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://fapi.asterdex.com/fapi/v3/exchangeInfo", timeout=15
                    ) as resp:
                        data = await resp.json()
                        aster_syms = {
                            s["symbol"]
                            for s in data["symbols"]
                            if s.get("status") == "TRADING"
                        }
                        self.symbols["asterdex"] = aster_syms
                        logger.info(
                            "symbol_inventory_loaded",
                            exchange="asterdex",
                            count=len(aster_syms),
                        )
            except Exception as e:
                logger.error(
                    "asterdex_symbol_inventory_failed", error=str(e)[:200]
                )

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.aden.io/api/v1/dex_futures/usdt/contracts",
                        timeout=15,
                    ) as resp:
                        data = await resp.json()
                        aden_syms = {
                            item["name"]
                            for item in data
                            if item.get("status") == "trading"
                        }
                        self.symbols["aden"] = aden_syms
                        logger.info(
                            "symbol_inventory_loaded",
                            exchange="aden",
                            count=len(aden_syms),
                        )
            except Exception as e:
                logger.error(
                    "aden_symbol_inventory_failed", error=str(e)[:200]
                )

            self._ready = True
            loaded = {k: len(v) for k, v in self.symbols.items()}
            logger.info("symbol_inventory_refresh_complete", exchanges=loaded)

    def has_symbol(self, exchange: str, symbol: str) -> bool:
        ex = EXCHANGE_NAME_MAP.get(exchange.lower().strip())
        if not ex:
            return True
        sym_set = self.symbols.get(ex)
        if sym_set is None:
            return True
        clean = normalize_symbol(symbol)
        if clean in sym_set:
            return True
        if f"{clean}:USDT" in sym_set or f"{clean}:USDC" in sym_set:
            return True
        return any(k.startswith(f"{clean}:") for k in sym_set)

    def get_exchange_symbols(self, exchange: str) -> List[str]:
        ex = EXCHANGE_NAME_MAP.get(exchange.lower().strip())
        if not ex:
            return []
        return sorted(self.symbols.get(ex, []))

    def get_all(self) -> Dict[str, List[str]]:
        return {FRONTEND_NAME_MAP.get(k, k): sorted(v) for k, v in self.symbols.items()}

    def get_markets(self, ex_id: str) -> Optional[dict]:
        ccxt_id = EXCHANGE_NAME_MAP.get(ex_id.lower().strip())
        return self.markets.get(ccxt_id)

    def get_all_markets(self) -> Dict[str, dict]:
        return dict(self.markets)


symbol_inventory = SymbolInventory()
