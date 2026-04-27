import asyncio
import json
import logging
import websockets
import aiohttp
from datetime import datetime
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
            "kucoin": self._kucoin_handler
        }
        self.callbacks: List[Callable] = []
        self.latest_rates: Dict[str, Dict[str, Any]] = {}
        # 增加緩衝區至 20000 筆，確保 Binance 巔峰流量不丟包
        self.queue = asyncio.Queue(maxsize=20000)

    def register_callback(self, callback: Callable):
        self.callbacks.append(callback)

    async def _notify_callbacks(self, data: Dict[str, Any]):
        """極速隊列寫入，不執行任何 IO 操作"""
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            # 溢出保護：移除最舊的一筆
            try: self.queue.get_nowait(); self.queue.put_nowait(data)
            except: pass

    async def _worker(self):
        """專用的後台處理器，負責 Redis 與 DB 的異步分發"""
        while True:
            try:
                data = await self.queue.get()
                key = f"{data['exchange']}:{data['symbol']}"
                self.latest_rates[key] = data
                for callback in self.callbacks:
                    try:
                        # 核心修復：使用 create_task 確保 Callback 不阻塞 Worker
                        if asyncio.iscoroutinefunction(callback):
                            asyncio.create_task(callback(data))
                        else:
                            callback(data)
                    except: pass
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Worker process error: {e}")

    async def start(self):
        # 啟動 10 個平行處理 Worker 應對 Binance 壓力
        for _ in range(10):
            asyncio.create_task(self._worker())
        
        tasks = []
        for name, handler in self.exchanges.items():
            tasks.append(asyncio.create_task(self._safe_handler(name, handler)))
        
        logger.info("Universal Data Stream Processor Online.")
        while True: await asyncio.sleep(3600)

    async def _safe_handler(self, name: str, handler: Callable):
        while True:
            try:
                await handler()
            except Exception as e:
                logger.error(f"Collector {name} disconnected: {e}. Reconnecting in 10s...")
                await asyncio.sleep(10)

    async def _binance_handler(self):
        url = "wss://fstream.binance.com/ws/!markPrice@arr"
        # 加強 Binance 的連線緩衝區設定
        async with websockets.connect(url, ping_interval=20, ping_timeout=15, max_size=2**24) as ws:
            logger.info("Connected: Binance Global Stream")
            while True:
                msg = await ws.recv()
                # 修復：回歸同步解析，防止 Task 爆炸
                data = json.loads(msg)
                for item in data:
                    await self._notify_callbacks({
                        "exchange": "binance", "symbol": item['s'], "rate": float(item['r']),
                        "settlement_time": datetime.fromtimestamp(item['T'] / 1000), "timestamp": datetime.utcnow()
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
            logger.info("Connected: OKX Strategy Hub")
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if "data" in data:
                    for item in data["data"]:
                        await self._notify_callbacks({
                            "exchange": "okx", "symbol": item['instId'].replace("-SWAP", "").replace("-", ""),
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
            sub = all_symbols[:100]
            await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{s}" for s in sub]}))
            logger.info("Connected: Bybit Linear")
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

    async def _bitget_handler(self):
        url = "wss://ws.bitget.com/v2/ws/public"
        async with websockets.connect(url, ping_interval=15) as ws:
            syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
            await ws.send(json.dumps({"op": "subscribe", "args": [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": s} for s in syms]}))
            logger.info("Connected: Bitget Advanced")
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
            await ws.send(json.dumps({"time": int(datetime.utcnow().timestamp()), "channel": "futures.tickers", "event": "subscribe", "payload": ["BTC_USDT", "ETH_USDT", "SOL_USDT"]}))
            logger.info("Connected: Gate.io Heatmap")
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("event") == "update":
                    results = data["result"]
                    items = results if isinstance(results, list) else [results]
                    for item in items:
                        await self._notify_callbacks({
                            "exchange": "gate", "symbol": item['contract'].replace("_", ""), "rate": float(item['funding_rate']),
                            "settlement_time": None, "timestamp": datetime.utcnow()
                        })

    async def _kucoin_handler(self):
        # 核心修復：更換 API 端點獲取真實 Funding Rate
        url = "https://api-futures.kucoin.com/api/v1/contracts/active"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, timeout=10) as resp:
                        res = await resp.json()
                        if res.get('data'):
                            for item in res['data']:
                                sym = item.get('symbol', '')
                                if 'USDT' in sym:
                                    clean_sym = sym.replace('USDTM', 'USDT').replace('-', '')
                                    rate = item.get('fundingFeeRate') # 核心修復：KuCoin 欄位名是 fundingFeeRate
                                    if rate is not None:
                                        await self._notify_callbacks({
                                            "exchange": "kucoin", "symbol": clean_sym,
                                            "rate": float(rate), "settlement_time": None, "timestamp": datetime.utcnow()
                                        })
                    await asyncio.sleep(60)
                except Exception as e:
                    logger.error(f"KuCoin critical poll error: {e}")
                    await asyncio.sleep(10)

collector = DataCollector()
