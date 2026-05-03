import asyncio
import json
import logging
import websockets
import aiohttp
import re
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
            # --- 全局過濾：檢查數據是否過期 ---
            items = data if isinstance(data, list) else [data]
            fresh_items = []
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            
            for item in items:
                settle_time = item.get('settlement_time')
                # 如果有結算時間，且結算時間已過，則視為過期
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
        logger.info("Universal Data Processor v17.0 (Global Filter) Active.")
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
        # 1. 抓取所有可能存在的 Ticker 作為種子 (全量掃描)
        seed_url = "https://api.coinw.com/api/v1/public?command=returnTicker"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(seed_url) as resp:
                res_data = await resp.json()
                all_raw_syms = res_data.get('data', {}).keys()
                # 抓取所有 USDT 幣種，不設上限
                all_pairs = list(set([s.split('_')[0] for s in all_raw_syms if 'USDT' in s]))
        
        wss_url = "wss://ws.futurescw.com/perpum"
        async with websockets.connect(wss_url, additional_headers=headers, ping_interval=15) as ws:
            # 2. 分批訂閱 (全量)
            for i in range(0, len(all_pairs), 30):
                batch = all_pairs[i:i+30]
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
                        await self._notify_callbacks({
                            "exchange": "coinw",
                            "symbol": f"{data.get('pairCode', '').upper()}USDT",
                            "rate": float(res["r"]),
                            "settlement_time": datetime.fromtimestamp(res["nt"] / 1000) if res.get("nt") else None,
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
                                    # KuCoin REST 沒有明確的 nextFundingTime，但通常 WSS 會推
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
