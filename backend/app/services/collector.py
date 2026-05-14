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

class IntervalManager:
    def __init__(self):
        self.intervals: Dict[str, Dict[str, int]] = {}
        self.lock = asyncio.Lock()

    async def refresh(self):
        async with self.lock:
            async with aiohttp.ClientSession() as session:
                # Binance
                try:
                    async with session.get("https://fapi.binance.com/fapi/v1/fundingInfo", timeout=10) as resp:
                        d = await resp.json()
                        self.intervals['binance'] = {i['symbol']: int(i.get('fundingIntervalHours', 8)) for i in d}
                except Exception as e:
                    logger.error(f"Binance Interval Refresh Failed: {e}")

                # Bybit
                try:
                    async with session.get("https://api.bybit.com/v5/market/instruments-info?category=linear", timeout=10) as resp:
                        d = await resp.json()
                        self.intervals['bybit'] = {i['symbol']: int(i.get('fundingInterval', 480)) // 60 for i in d['result']['list']}
                except Exception as e:
                    logger.error(f"Bybit Interval Refresh Failed: {e}")

                # Bitget
                try:
                    async with session.get("https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES", timeout=10) as resp:
                        d = await resp.json()
                        if d.get('code') == '00000':
                            self.intervals['bitget'] = {i['symbol']: int(i.get('fundInterval', 8)) for i in d['data']}
                except Exception as e:
                    logger.error(f"Bitget Interval Refresh Failed: {e}")

                # Gate
                try:
                    async with session.get("https://api.gateio.ws/api/v4/futures/usdt/contracts", timeout=10) as resp:
                        d = await resp.json()
                        self.intervals['gate'] = {i['name']: int(i.get('funding_interval', 28800)) // 3600 for i in d}
                except Exception as e:
                    logger.error(f"Gate Interval Refresh Failed: {e}")

                # CoinW
                try:
                    async with session.get("https://api.coinw.com/v1/perpum/instruments", timeout=10) as resp:
                        d = await resp.json()
                        if d.get('code') == 0:
                            # Normalize CoinW symbols to match collector (BTCUSDT)
                            self.intervals['coinw'] = {i['base'].upper() + "USDT": int(i.get('settledPeriod', 8)) for i in d['data']}
                except Exception as e:
                    logger.error(f"CoinW Interval Refresh Failed: {e}")

                # MEXC
                try:
                    async with session.get("https://contract.mexc.com/api/v1/contract/funding_rate", timeout=10) as resp:
                        d = await resp.json()
                        if d.get('success'):
                            self.intervals['mexc'] = {i['symbol']: int(i.get('collectCycle', 8)) for i in d['data']}
                except Exception as e:
                    logger.error(f"MEXC Interval Refresh Failed: {e}")

                # KuCoin
                try:
                    async with session.get("https://api-futures.kucoin.com/api/v1/contracts/active", timeout=10) as resp:
                        d = await resp.json()
                        if d.get('code') == '200000':
                            self.intervals['kucoin'] = {i['symbol']: int(i.get('fundingRateGranularity') or 28800000) // 3600000 for i in d['data']}
                except Exception as e:
                    logger.error(f"KuCoin Interval Refresh Failed: {e}")

                # BingX
                try:
                    async with session.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", timeout=10) as resp:
                        d = await resp.json()
                        if d.get('code') == 0:
                            self.intervals['bingx'] = {i['symbol']: int(i.get('fundingIntervalHours', 8)) for i in d['data']}
                except Exception as e:
                    logger.error(f"BingX Interval Refresh Failed: {e}")

        logger.info(f"Interval Map Refreshed. (Binance: {len(self.intervals.get('binance', {}))}, Bybit: {len(self.intervals.get('bybit', {}))}, Bitget: {len(self.intervals.get('bitget', {}))}, MEXC: {len(self.intervals.get('mexc', {}))})")

    def get(self, exchange: str, symbol: str) -> int:
        exch = exchange.lower().strip()
        # 符號正規化以適應快取查找 (例如 BTC-USDT -> BTCUSDT)
        clean_sym = re.sub(r'(-|/|_|SWAP|PERP|M$)', '', symbol).upper()
        
        ex_map = self.intervals.get(exch, {})
        
        # 特殊處理 Binance 的幣種符號 (Binance API 往往不帶橫線)
        if exch == 'binance':
            return ex_map.get(clean_sym, 8)
            
        # 優先查找原始符號，然後是正規化後的匹配
        return ex_map.get(symbol, ex_map.get(clean_sym, 8))

interval_manager = IntervalManager()

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
            "bingx": self._bingx_handler,
            "aden": self._aden_handler,
            "hyperliquid": self._hyperliquid_handler,
            "asterdex": self._asterdex_handler,
            "lighter": self._lighter_handler
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
                        exch = item.get('exchange', '?')
                        sym = item.get('symbol', '?')
                        logger.warning(f"Settlement expired: {exch} {sym}, settle={settle_time}")
                        continue
                
                exch = item['exchange']
                sym = item['symbol']
                item['interval'] = item.get('interval') or interval_manager.get(exch, sym)
                fresh_items.append(item)
            
            if not fresh_items:
                if isinstance(data, list) and len(items) > 0:
                    logger.warning(f"All {len(items)} items filtered out in notify_callbacks")
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
                    try:
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
                            except Exception as cb_err:
                                logger.error(f"Callback error for {key}: {cb_err}")
                    except Exception as item_err:
                        logger.error(f"Worker item processing error: {item_err} | item keys={list(item.keys()) if isinstance(item, dict) else type(item)}")
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Worker fatal error: {e}")
                await asyncio.sleep(1)

    async def start(self):
        await interval_manager.refresh()
        asyncio.create_task(self._interval_refresher())
        
        for _ in range(15): asyncio.create_task(self._worker())
        for name, handler in self.exchanges.items():
            asyncio.create_task(self._safe_handler(name, handler))
        logger.info("Universal Data Processor v19.2 Online.")
        while True: await asyncio.sleep(3600)

    async def _interval_refresher(self):
        while True:
            await asyncio.sleep(86400) # Daily refresh
            await interval_manager.refresh()

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
                    # 獲取交易中合約清單以過濾 PENDING_TRADING 或 SETTLING (如 RLS, OXT)
                    async with session.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=10) as ex_resp:
                        ex_info = await ex_resp.json()
                        trading_syms = {s['symbol'] for s in ex_info['symbols'] if s['status'] == 'TRADING'}

                    async with session.get(url, timeout=10) as resp:
                        data = await resp.json()
                        batch = [{
                            "exchange": "binance", "symbol": item['symbol'], "rate": float(item['lastFundingRate']),
                            "mark_price": float(item['markPrice']) if item.get('markPrice') else None,
                            "settlement_time": datetime.fromtimestamp(item['nextFundingTime'] / 1000), "timestamp": datetime.utcnow()
                        } for item in data if item.get('symbol') in trading_syms]
                        await self._notify_callbacks(batch)
                    await asyncio.sleep(30)
                except Exception as e:
                    logger.error(f"Binance Handler Failed: {e}")
                    await asyncio.sleep(10)

    async def _coinw_handler(self):
        # --- 核心：探測與輪詢輔助 ---
        wss_url = "wss://ws.futurescw.com/perpum"
        rest_base = "https://api.coinw.com"
        
        async def get_all_futures():
            try:
                # 優先檢查 IntervalManager 是否已經有成功的 CoinW 清單 (避免重複請求觸發 429)
                cached_coinw = interval_manager.intervals.get('coinw')
                if cached_coinw:
                    return [s.replace('USDT', '') for s in cached_coinw.keys()]

                # 嘗試使用 REST API 探測
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{rest_base}/v1/perpum/instruments", timeout=10) as resp:
                        res = await resp.json()
                        if res.get('code') == 0 and 'data' in res:
                            return list(set([item['base'].upper() for item in res['data'] if item.get('status') == 'online']))
                
                return ["BTC", "ETH", "SOL", "CHIP", "LUNC", "DOGE", "PEPE"]
            except Exception as e:
                logger.error(f"CoinW Discovery failed: {e}")
                return ["BTC", "ETH", "SOL", "CHIP", "LUNC", "DOGE", "PEPE"]

        async def poll_task(pairs):
            """補足 WS 可能漏掉的數據，每 10 分鐘全面輪詢一次"""
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        for p in pairs:
                            url = f"{rest_base}/v1/perpum/fundingRate?instrument={p.lower()}"
                            async with session.get(url, timeout=5) as resp:
                                res = await resp.json()
                                if res.get('code') == 0 and 'data' in res:
                                    item = res['data']
                                    await self._notify_callbacks({
                                        "exchange": "coinw",
                                        "symbol": f"{p.upper()}USDT",
                                        "rate": float(item['value']),
                                        "settlement_time": None,
                                        "timestamp": datetime.utcnow()
                                    })
                            await asyncio.sleep(0.15)
                        await asyncio.sleep(600)
                    except Exception as e:
                        logger.error(f"CoinW Polling Error: {e}")
                        await asyncio.sleep(30)

        pairs = await get_all_futures()
        if "CHIP" not in pairs: pairs.append("CHIP")
        logger.info(f"CoinW Discovery Success: {len(pairs)} pairs. Starting WS & Polling.")
        
        # 啟動補位輪詢
        asyncio.create_task(poll_task(pairs))

        additional_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with websockets.connect(wss_url, additional_headers=additional_headers, ping_interval=15) as ws:
            # 分批訂閱 funding_rate + mark_price
            for i in range(0, len(pairs), 40):
                batch = pairs[i:i+40]
                for p in batch:
                    await ws.send(json.dumps({"event": "sub", "params": {"biz": "futures", "type": "funding_rate", "pairCode": p}}))
                    await ws.send(json.dumps({"event": "sub", "params": {"biz": "futures", "type": "mark_price", "pairCode": p}}))
                await asyncio.sleep(1)
            
            mark_prices = {}
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                msg_type = data.get("type", "")
                
                if msg_type == "mark_price" and "data" in data:
                    d = data["data"]
                    if "p" in d:
                        pair = data.get("pairCode", "").lower()
                        try:
                            mark_prices[pair] = float(d["p"])
                        except: pass
                
                elif msg_type == "funding_rate" and "data" in data:
                    res = data["data"]
                    if "r" in res:
                        pair = data.get("pairCode", "").lower()
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
                            "mark_price": mark_prices.get(pair),
                            "settlement_time": next_settle_dt if next_settle_ms else None,
                            "timestamp": datetime.utcnow()
                        })

    async def _okx_handler(self):
        url = "wss://ws.okx.com:8443/ws/v5/public"
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP") as resp:
                d = await resp.json()
                # 僅訂閱 'live' 狀態的合約
                all_ids = [i['instId'] for i in d['data'] if i['settleCcy'] == 'USDT' and i.get('state') == 'live']
        async with websockets.connect(url, ping_interval=20) as ws:
            for i in range(0, len(all_ids), 100):
                batch = all_ids[i:i+100]
                await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "funding-rate", "instId": inst_id} for inst_id in batch]}))
            for i in range(0, len(all_ids), 100):
                batch = all_ids[i:i+100]
                await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "mark-price", "instId": inst_id} for inst_id in batch]}))

            mark_prices = {}
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if "data" not in data:
                    continue
                channel = data.get("arg", {}).get("channel", "")

                if channel == "mark-price":
                    for item in data["data"]:
                        try:
                            mark_prices[item['instId']] = float(item.get('markPx', 0))
                        except: pass
                elif channel == "funding-rate":
                    for item in data["data"]:
                        interval = 8
                        if 'nextFundingTime' in item and 'fundingTime' in item:
                            try:
                                interval = max(1, round((int(item['nextFundingTime']) - int(item['fundingTime'])) / 3600000))
                            except: pass
                        await self._notify_callbacks({
                            "exchange": "okx", "symbol": item['instId'],
                            "rate": float(item['fundingRate']),
                            "mark_price": mark_prices.get(item['instId']),
                            "settlement_time": datetime.fromtimestamp(int(item['nextFundingTime']) / 1000),
                            "interval": interval,
                            "timestamp": datetime.utcnow()
                        })

    async def _bybit_handler(self):
        url = "wss://stream.bybit.com/v5/public/linear"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://api.bybit.com/v5/market/instruments-info?category=linear") as resp:
                    d = await resp.json()
                    # 僅訂閱 'Trading' 狀態
                    all_symbols = [i['symbol'] for i in d['result']['list'] if i['symbol'].endswith('USDT') and i.get('status') == 'Trading']
                
                # 初始 REST 抓取：確保秒開有數據
                async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as resp:
                    d = await resp.json()
                    batch = []
                    for item in d.get('result', {}).get('list', []):
                        if item['symbol'] in all_symbols and item.get('fundingRate'):
                            batch.append({
                                "exchange": "bybit", "symbol": item['symbol'], "rate": float(item['fundingRate']),
                                "mark_price": float(item['markPrice']) if item.get('markPrice') else None,
                                "settlement_time": datetime.fromtimestamp(int(item['nextFundingTime']) / 1000) if item.get('nextFundingTime') else None,
                                "timestamp": datetime.utcnow()
                            })
                    if batch: await self._notify_callbacks(batch)
            except Exception as e: logger.error(f"Bybit Initial Fetch Failed: {e}")
        async with websockets.connect(url, ping_interval=20) as ws:
            for i in range(0, len(all_symbols), 100):
                batch = all_symbols[i:i+100]
                await ws.send(json.dumps({"op": "subscribe", "args": [f"tickers.{s}" for s in batch]}))
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if "topic" in data and data["topic"].startswith("tickers"):
                    item = data["data"]
                    if "fundingRate" in item:
                        await self._notify_callbacks({
                            "exchange": "bybit", "symbol": item['symbol'], "rate": float(item['fundingRate']),
                            "mark_price": float(item['markPrice']) if 'markPrice' in item and item['markPrice'] else None,
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
                                if 'USDT' in item.get('symbol', '') and item.get('status') == 'Open':
                                    sym = item['symbol'].replace('XBT', 'BTC')
                                    await self._notify_callbacks({
                                        "exchange": "kucoin", "symbol": sym,
                                        "rate": float(item.get('fundingFeeRate') or 0),
                                        "mark_price": float(item['markPrice']) if item.get('markPrice') else None,
                                        "interval": int(item.get('fundingRateGranularity') or 28800000) // 3600000,
                                        "settlement_time": datetime.fromtimestamp(item['nextFundingRateDateTime'] / 1000) if item.get('nextFundingRateDateTime') else None, 
                                        "timestamp": datetime.utcnow()
                                    })
                    await asyncio.sleep(30)
                except: await asyncio.sleep(10)

    async def _mexc_handler(self):
        url = "https://contract.mexc.com/api/v1/contract/funding_rate"
        ticker_url = "https://contract.mexc.com/api/v1/contract/ticker"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # Fetch mark prices from ticker (MEXC uses 'fairPrice' as mark price)
                    mark_prices = {}
                    async with session.get(ticker_url, timeout=10) as t_resp:
                        t_data = await t_resp.json()
                        if t_data.get('success') and t_data.get('data'):
                            for t in t_data['data']:
                                price = t.get('fairPrice') or t.get('indexPrice')
                                if price:
                                    mark_prices[t['symbol']] = float(price)

                    # 獲取 MEXC 合約詳情以過濾狀態 (state 0 為正常交易)
                    async with session.get("https://contract.mexc.com/api/v1/contract/detail", timeout=10) as det_resp:
                        det_data = await det_resp.json()
                        trading_syms = {i['symbol'] for i in det_data['data'] if i.get('state') == 0}

                    async with session.get(url, timeout=10) as resp:
                        d = await resp.json()
                        if d.get('data'):
                            for item in d['data']:
                                if item['symbol'] in trading_syms:
                                    await self._notify_callbacks({
                                        "exchange": "mexc", "symbol": item['symbol'], "rate": float(item['fundingRate']),
                                        "mark_price": mark_prices.get(item['symbol']),
                                        "settlement_time": datetime.fromtimestamp(item['nextSettleTime'] / 1000) if item.get('nextSettleTime') else None,
                                        "interval": int(item.get('collectCycle', 8)),
                                        "timestamp": datetime.utcnow()
                                    })
                    await asyncio.sleep(30)
                except: await asyncio.sleep(15)

    async def _bingx_handler(self):
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # 獲取 BingX 合約清單以過濾狀態 (status 1 為正常交易)
                    async with session.get("https://open-api.bingx.com/openApi/swap/v2/quote/contracts") as c_resp:
                        c_data = await c_resp.json()
                        trading_syms = {i['symbol'] for i in c_data['data'] if i.get('status') == 1}

                    async with session.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex") as resp:
                        d = await resp.json()
                        if d.get('data'):
                            for item in d['data']:
                                if item['symbol'] in trading_syms and item['symbol'].endswith('USDT'):
                                    await self._notify_callbacks({
                                        "exchange": "bingx", "symbol": item['symbol'], "rate": float(item['lastFundingRate']),
                                        "mark_price": float(item['markPrice']) if item.get('markPrice') else None,
                                        "settlement_time": datetime.fromtimestamp(item['nextFundingTime'] / 1000) if item.get('nextFundingTime') else None,
                                        "interval": int(item.get('fundingIntervalHours', 8)),
                                        "timestamp": datetime.utcnow()
                                    })
                    await asyncio.sleep(30)
                except: await asyncio.sleep(15)

    async def _bitget_handler(self):
        url = "wss://ws.bitget.com/v2/ws/public"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES") as resp:
                    d = await resp.json()
                    # 僅訂閱 'normal' 狀態
                    all_symbols = [i['symbol'] for i in d['data'] if i['symbolStatus'] == 'normal' and i['quoteCoin'] == 'USDT']
                
                # 初始 REST 抓取
                async with session.get("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES") as resp:
                    d = await resp.json()
                    batch = []
                    for item in d.get('data', []):
                        if item['symbol'] in all_symbols and item.get('fundingRate'):
                            mp = item.get('markPrice') or item.get('markPr') or item.get('markPx')
                            batch.append({
                                "exchange": "bitget", "symbol": item['symbol'], "rate": float(item['fundingRate']),
                                "mark_price": float(mp) if mp else None,
                                "settlement_time": datetime.fromtimestamp(int(item['nextFundingTime']) / 1000) if item.get('nextFundingTime') else None,
                                "timestamp": datetime.utcnow()
                            })
                    if batch: await self._notify_callbacks(batch)
            except Exception as e: logger.error(f"Bitget Initial Fetch Failed: {e}")
        
        async with websockets.connect(url, ping_interval=15) as ws:
            for i in range(0, len(all_symbols), 100):
                batch = all_symbols[i:i+100]
                await ws.send(json.dumps({"op": "subscribe", "args": [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": s} for s in batch]}))
            
            while True:
                msg = await ws.recv()
                if msg == "pong": continue
                data = json.loads(msg)
                if "data" in data:
                    for item in data["data"]:
                        if "fundingRate" in item:
                            mp = item.get('markPrice') or item.get('markPr') or item.get('markPx')
                            await self._notify_callbacks({
                                "exchange": "bitget", "symbol": item['instId'], "rate": float(item['fundingRate']),
                                "mark_price": float(mp) if mp else None,
                                "settlement_time": datetime.fromtimestamp(int(item['nextFundingTime']) / 1000) if item.get('nextFundingTime') else None,
                                "timestamp": datetime.utcnow()
                            })

    async def _gate_handler(self):
        url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://api.gateio.ws/api/v4/futures/usdt/contracts") as resp:
                    d = await resp.json()
                    # 僅訂閱 'trading' 狀態
                    all_symbols = [i['name'] for i in d if i.get('status') == 'trading']
                
                # 初始 REST 抓取
                async with session.get("https://api.gateio.ws/api/v4/futures/usdt/tickers") as resp:
                    d = await resp.json()
                    batch = []
                    for item in d:
                        if item['contract'] in all_symbols and item.get('funding_rate'):
                            batch.append({
                                "exchange": "gate", "symbol": item['contract'], "rate": float(item['funding_rate']),
                                "mark_price": float(item['mark_price']) if item.get('mark_price') else None,
                                "settlement_time": None, "timestamp": datetime.utcnow()
                            })
                    if batch: await self._notify_callbacks(batch)
            except Exception as e: logger.error(f"Gate Initial Fetch Failed: {e}")
        
        async with websockets.connect(url, ping_interval=20) as ws:
            for i in range(0, len(all_symbols), 100):
                batch = all_symbols[i:i+100]
                await ws.send(json.dumps({
                    "time": int(datetime.utcnow().timestamp()), 
                    "channel": "futures.tickers", 
                    "event": "subscribe", 
                    "payload": batch
                }))
            
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("event") == "update":
                    results = data["result"]
                    items = results if isinstance(results, list) else [results]
                    for item in items:
                        await self._notify_callbacks({
                            "exchange": "gate", "symbol": item['contract'], "rate": float(item['funding_rate']),
                            "mark_price": float(item['mark_price']) if item.get('mark_price') else None,
                            "settlement_time": None, "timestamp": datetime.utcnow()
                        })

    async def _aden_handler(self):
        """
        Aden DEX aggregator — uses api.aden.io (NOT perp-api.aden.io).
        Endpoint: GET /api/v1/dex_futures/usdt/contracts → returns ALL 634+ perpetual pairs
        with per-contract funding_rate, mark_price, funding_interval (seconds),
        funding_next_apply (unix ts), and status.
        Symbol format: DRIFT_USDT → worker normalizes to DRIFTUSDT.
        """
        url = "https://api.aden.io/api/v1/dex_futures/usdt/contracts"
        inventory_logged = False
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not inventory_logged:
                                names = sorted([x['name'] for x in data if x.get('name')])
                                logger.info(f"Aden Inventory ({len(names)} contracts via api.aden.io):")
                                for n in names:
                                    logger.info(f"  Aden: {n}")
                                inventory_logged = True

                            batch = []
                            for item in data:
                                name = item.get('name', '')
                                if not name or item.get('status') != 'trading':
                                    continue
                                rate = item.get('funding_rate')
                                if rate is None:
                                    logger.warning(f"Aden {name}: missing funding_rate, skipping")
                                    continue
                                mark_price = item.get('mark_price')
                                interval = int(item.get('funding_interval', 28800)) // 3600
                                settle_ts = item.get('funding_next_apply')
                                settle_time = datetime.fromtimestamp(settle_ts) if settle_ts else None
                                batch.append({
                                    "exchange": "aden",
                                    "symbol": name,
                                    "rate": float(rate),
                                    "mark_price": float(mark_price) if mark_price else None,
                                    "settlement_time": settle_time,
                                    "interval": interval,
                                    "timestamp": datetime.utcnow()
                                })
                            if batch:
                                await self._notify_callbacks(batch)
                            else:
                                logger.warning("Aden: empty batch after processing")
                    await asyncio.sleep(30)
                except Exception as e:
                    logger.error(f"Aden Handler Failed: {e}")
                    await asyncio.sleep(15)

    async def _hyperliquid_handler(self):
        """Hyperliquid DEX — REST API: POST /info with type=metaAndAssetCtxs
        Returns 230 USDC perpetual pairs with funding, markPx, openInterest, etc.
        All pairs have a 1-hour funding interval.
        Symbol format: BTC/USDC:USDC → worker cleans to BTCUSDC
        """
        url = "https://api.hyperliquid.xyz/info"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.post(url, json={"type": "metaAndAssetCtxs"}, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            meta = data[0]
                            ctxs = data[1]
                            batch = []
                            for m, c in zip(meta['universe'], ctxs):
                                name = m['name']
                                funding = c.get('funding')
                                if funding is None:
                                    continue
                                mark = c.get('markPx')
                                batch.append({
                                    "exchange": "hyperliquid",
                                    "symbol": f"{name}/USDC:USDC",
                                    "rate": float(funding),
                                    "mark_price": float(mark) if mark else None,
                                    "interval": 1,
                                    "timestamp": datetime.utcnow()
                                })
                            if batch:
                                await self._notify_callbacks(batch)
                    await asyncio.sleep(30)
                except Exception as e:
                    logger.error(f"Hyperliquid Handler Failed: {e}")
                    await asyncio.sleep(15)

    async def _asterdex_handler(self):
        """AsterDEX DEX — REST API: GET /fapi/v3/premiumIndex (Binance-variant API)
        Returns 400+ USDT perpetual pairs with markPrice, lastFundingRate, nextFundingTime.
        Base URL: https://fapi.asterdex.com
        Symbol format: BTCUSDT — clean, no normalization needed.
        """
        pairs_url = "https://fapi.asterdex.com/fapi/v3/premiumIndex"
        info_url = "https://fapi.asterdex.com/fapi/v3/exchangeInfo"
        fund_url = "https://fapi.asterdex.com/fapi/v3/fundingInfo"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(info_url, timeout=15) as info_resp:
                        info = await info_resp.json()
                        trading_syms = {s['symbol'] for s in info['symbols'] if s.get('status') == 'TRADING'}

                    intervals = {}
                    async with session.get(fund_url, timeout=15) as fund_resp:
                        fi = await fund_resp.json()
                        intervals = {x['symbol']: int(x.get('fundingIntervalHours', 8)) for x in fi}

                    async with session.get(pairs_url, timeout=15) as resp:
                        data = await resp.json()
                        batch = []
                        for item in data:
                            sym = item.get('symbol', '')
                            if sym not in trading_syms:
                                continue
                            rate = item.get('lastFundingRate')
                            if rate is None:
                                continue
                            mark = item.get('markPrice')
                            next_ts = item.get('nextFundingTime')
                            settle_time = datetime.fromtimestamp(next_ts / 1000) if next_ts else None
                            interval = intervals.get(sym, 8)
                            batch.append({
                                "exchange": "asterdex",
                                "symbol": sym,
                                "rate": float(rate),
                                "mark_price": float(mark) if mark else None,
                                "settlement_time": settle_time,
                                "interval": interval,
                                "timestamp": datetime.utcnow()
                            })
                        if batch:
                            await self._notify_callbacks(batch)
                    await asyncio.sleep(30)
                except Exception as e:
                    logger.error(f"AsterDEX Handler Failed: {e}")
                    await asyncio.sleep(15)

    async def _lighter_handler(self):
        """Lighter DEX — via CCXT (public, no API key needed).
        fetchFundingRates() returns ~167 USDC perpetual pairs.
        Note: CCXT does not return markPrice or nextFundingTimestamp for Lighter.
        Symbol format: LINK/USDC:USDC → worker cleans to LINKUSDC.
        """
        while True:
            try:
                def sync_fetch():
                    ex = ccxt_sync.lighter()
                    return ex.fetch_funding_rates()
                rates = await asyncio.to_thread(sync_fetch)
                batch = []
                for sym, rate in rates.items():
                    fr = rate.get('fundingRate')
                    if fr is None:
                        continue
                    batch.append({
                        "exchange": "lighter",
                        "symbol": sym,
                        "rate": float(fr),
                        "mark_price": None,
                        "interval": 1,
                        "timestamp": datetime.utcnow()
                    })
                if batch:
                    await self._notify_callbacks(batch)
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Lighter Handler Failed: {e}")
                await asyncio.sleep(15)

collector = DataCollector()
