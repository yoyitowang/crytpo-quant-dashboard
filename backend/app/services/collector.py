import asyncio
import json
import logging
import websockets
import aiohttp
import re
import ccxt as ccxt_sync
from datetime import datetime, timezone
from typing import List, Dict, Any, Callable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataCollector:
    def __init__(self):
        self.exchanges = {
            "binance": self._binance_handler,
            "okx": self._okx_handler,
            "bybit": self._bybit_handler,
            "bitget": self._bitget_handler,
            "gate": self._gate_handler,
            "kucoin": self._kucoin_handler,
            "coinw": self._coinw_handler, 
            "mexc": self._mexc_handler,
            "bingx": self._bingx_handler
        }
        self.callbacks: List[Callable] = []
        self.latest_rates: Dict[str, Dict[str, Any]] = {}
        self.queue = asyncio.Queue(maxsize=50000)

    def register_callback(self, callback: Callable):
        self.callbacks.append(callback)

    async def _notify_callbacks(self, data: Any):
        try:
            items = data if isinstance(data, list) else [data]
            fresh_items = []
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
            for item in items:
                settle_time = item.get('settlement_time')
                if settle_time and isinstance(settle_time, datetime):
                    if settle_time < now:
                        continue
                fresh_items.append(item)
            
            if not fresh_items:
                return

            msg = fresh_items if isinstance(data, list) else fresh_items[0]
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            try: 
                self.queue.get_nowait()
                self.queue.put_nowait(msg)
            except: pass
        except Exception as e:
            logger.error(f"Notify Error: {e}")

    async def _worker(self):
        while True:
            try:
                data = await self.queue.get()
                items = data if isinstance(data, list) else [data]
                for item in items:
                    exch = str(item['exchange']).lower().strip()
                    raw_sym = str(item['symbol']).upper()
                    clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', raw_sym)
                    key = f"latest:{exch}:{clean_sym}"
                    item['exchange'] = exch
                    item['symbol'] = clean_sym
                    self.latest_rates[key] = item
                    for callback in self.callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback): asyncio.create_task(callback(item))
                            else: callback(item)
                        except: pass
                self.queue.task_done()
            except Exception: pass

    async def start(self):
        for _ in range(15): asyncio.create_task(self._worker())
        for name, handler in self.exchanges.items():
            asyncio.create_task(self._safe_handler(name, handler))
        logger.info("Universal Data Processor v18.6 Online.")
        while True: await asyncio.sleep(3600)

    async def _safe_handler(self, name: str, handler: Callable):
        while True:
            try: await handler()
            except Exception as e:
                logger.error(f"Collector {name} crashed: {e}")
                await asyncio.sleep(20)

    async def _binance_handler(self):
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, timeout=10) as resp:
                        data = await resp.json()
                        batch = [{
                            "exchange": "binance", "symbol": item['symbol'], "rate": float(item['lastFundingRate']),
                            "settlement_time": datetime.fromtimestamp(item['nextFundingTime'] / 1000), "timestamp": datetime.utcnow()
                        } for item in data if 'symbol' in item]
                        await self._notify_callbacks(batch)
                    await asyncio.sleep(60)
                except: await asyncio.sleep(10)

    async def _coinw_handler(self):
        # --- 核心：利用 CCXT 精確探測全市場期貨幣種 ---
        wss_url = "wss://ws.futurescw.com/perpum"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        async def get_all_futures():
            try:
                # 使用 CCXT 4.5.51+ 正確加載 CoinW 合約清單
                import ccxt.async_support as ccxt_async
                exchange = ccxt_async.coinw()
                markets = await exchange.load_markets()
                # 篩選 Swap 且結算為 USDT 的幣種
                futures = [m['base'] for m in markets.values() if m.get('swap') and m.get('settle') == 'USDT']
                await exchange.close()
                return list(set(futures))
            except Exception as e:
                logger.error(f"CoinW CCXT Discovery failed: {e}")
                # 備援機制：至少包含主流與用戶要求
                return ["BTC", "ETH", "SOL", "CHIP", "LUNC", "DOGE", "PEPE"]

        additional_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        async with websockets.connect(wss_url, additional_headers=additional_headers, ping_interval=15) as ws:
            pairs = await get_all_futures()
            # 確保 CHIP 在清單中
            if "CHIP" not in [p.upper() for p in pairs]:
                pairs.append("CHIP")
                
            logger.info(f"CoinW Discovery Success: Subscribing to {len(pairs)} Pure Futures.")

            # 分批訂閱
            for i in range(0, len(pairs), 40):
                batch = pairs[i:i+40]
                for p in batch:
                    sub_msg = {"event": "sub", "params": {"biz": "futures", "type": "funding_rate", "pairCode": p}}
                    await ws.send(json.dumps(sub_msg))
                await asyncio.sleep(1)
            
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("type") == "funding_rate" and "data" in data:
                    res = data["data"]
                    if "r" in res:
                        # 過期過濾
                        next_settle_ms = res.get("nt")
                        if next_settle_ms:
                            next_settle_dt = datetime.fromtimestamp(next_settle_ms / 1000)
                            if next_settle_dt < datetime.now().replace(tzinfo=None):
                                continue
                        
                        await self._notify_callbacks({
                            "exchange": "coinw",
                            "symbol": f"{data.get('pairCode', '').upper()}USDT",
                            "rate": float(res["r"]),
                            "settlement_time": next_settle_dt if next_settle_ms else None,
                            "timestamp": datetime.utcnow()
                        })

    async def _okx_handler(self):
        url = "wss://ws.okx.com:8443/ws/v5/public"
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP") as resp:
                d = await resp.json()
                all_ids = [i['instId'] for i in d['data'] if i['settleCcy'] == 'USDT']
        async with websockets.connect(url, ping_interval=20) as ws:
            for i in range(0, len(all_ids), 100):
                batch = all_ids[i:i+100]
                await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "funding-rate", "instId": inst_id} for inst_id in batch]}))
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if "data" in data:
                    for item in data["data"]:
                        await self._notify_callbacks({
                            "exchange": "okx", "symbol": item['instId'],
                            "rate": float(item['fundingRate']), "settlement_time": datetime.fromtimestamp(int(item['fundingTime']) / 1000),
                            "timestamp": datetime.utcnow()
                        })

    async def _bybit_handler(self):
        url = "wss://stream.bybit.com/v5/public/linear"
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.bybit.com/v5/market/instruments-info?category=linear") as resp:
                d = await resp.json()
                all_symbols = [i['symbol'] for i in d['result']['list'] if i['symbol'].endswith('USDT')]
        async with websockets.connect(url, ping_interval=20) as ws:
            sub = all_symbols[:150]
            await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{s}" for s in sub]}))
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if "topic" in data and data["topic"].startswith("tickers"):
                    item = data["data"]
                    if "fundingRate" in item:
                        await self._notify_callbacks({
                            "exchange": "bybit", "symbol": item['symbol'], "rate": float(item['fundingRate']),
                            "settlement_time": datetime.fromtimestamp(int(item['nextFundingTime']) / 1000) if 'nextFundingTime' in item else None,
                            "timestamp": datetime.utcnow()
                        })

    async def _kucoin_handler(self):
        url = "https://api-futures.kucoin.com/api/v1/contracts/active"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, timeout=10) as resp:
                        res = await resp.json()
                        if res.get('data'):
                            for item in res['data']:
                                if 'USDT' in item.get('symbol', ''):
                                    await self._notify_callbacks({
                                        "exchange": "kucoin", "symbol": item['symbol'],
                                        "rate": float(item.get('fundingFeeRate') or 0), "settlement_time": None, "timestamp": datetime.utcnow()
                                    })
                    await asyncio.sleep(60)
                except: await asyncio.sleep(10)

    async def _mexc_handler(self):
        url = "https://contract.mexc.com/api/v1/contract/funding_rate"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, timeout=10) as resp:
                        d = await resp.json()
                        if d.get('data'):
                            for item in d['data']:
                                await self._notify_callbacks({
                                    "exchange": "mexc", "symbol": item['symbol'], "rate": float(item['fundingRate']),
                                    "settlement_time": datetime.fromtimestamp(item['settleTime'] / 1000) if item.get('settleTime') else None,
                                    "timestamp": datetime.utcnow()
                                })
                    await asyncio.sleep(60)
                except: await asyncio.sleep(15)

    async def _bingx_handler(self):
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex") as resp:
                        d = await resp.json()
                        if d.get('data'):
                            for item in d['data']:
                                if item['symbol'].endswith('USDT'):
                                    await self._notify_callbacks({
                                        "exchange": "bingx", "symbol": item['symbol'], "rate": float(item['lastFundingRate']),
                                        "settlement_time": datetime.fromtimestamp(item['nextFundingTime'] / 1000) if item.get('nextFundingTime') else None,
                                        "timestamp": datetime.utcnow()
                                    })
                    await asyncio.sleep(60)
                except: await asyncio.sleep(15)

    async def _bitget_handler(self):
        url = "wss://ws.bitget.com/v2/ws/public"
        async with websockets.connect(url, ping_interval=15) as ws:
            syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
            await ws.send(json.dumps({"op": "subscribe", "args": [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": s} for s in syms]}))
            while True:
                msg = await ws.recv()
                if msg == "pong": continue
                data = json.loads(msg)
                if "data" in data:
                    for item in data["data"]:
                        if "fundingRate" in item:
                            await self._notify_callbacks({
                                "exchange": "bitget", "symbol": item['instId'], "rate": float(item['fundingRate']),
                                "settlement_time": datetime.fromtimestamp(int(item['nextFundingTime']) / 1000) if item.get('nextFundingTime') else None,
                                "timestamp": datetime.utcnow()
                            })

    async def _gate_handler(self):
        url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
        async with websockets.connect(url, ping_interval=20) as ws:
            await ws.send(json.dumps({"time": int(datetime.utcnow().timestamp()), "channel": "futures.tickers", "event": "subscribe", "payload": ["BTC_USDT", "ETH_USDT", "SOL_USDT", "DOGE_USDT"]}))
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("event") == "update":
                    results = data["result"]
                    items = results if isinstance(results, list) else [results]
                    for item in items:
                        await self._notify_callbacks({
                            "exchange": "gate", "symbol": item['contract'], "rate": float(item['funding_rate']),
                            "settlement_time": None, "timestamp": datetime.utcnow()
                        })

collector = DataCollector()
