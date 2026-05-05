import asyncio
import json
import websockets
import logging
import redis
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Discovery")

async def discover():
    # 1. Get candidates from other exchanges in Redis
    r = redis.Redis(host='redis', port=6379, decode_responses=True)
    all_keys = r.keys("latest:*")
    candidates = set()
    for k in all_keys:
        parts = k.split(":")
        if len(parts) == 3:
            sym = parts[2]
            # Strip common suffixes just in case
            base = sym.replace("USDT", "").replace("USDC", "")
            candidates.add(base)
    
    logger.info(f"Collected {len(candidates)} candidates from Redis.")

    # 2. Start WSS and probe in batches
    url = "wss://ws.futurescw.com/perpum"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    active = set()
    
    try:
        async with websockets.connect(url, extra_headers=headers, ping_interval=15) as ws:
            candidates_list = list(candidates)
            for i in range(0, len(candidates_list), 50):
                batch = candidates_list[i:i+50]
                for p in batch:
                    sub_msg = {"event": "sub", "params": {"biz": "futures", "type": "funding_rate", "pairCode": p}}
                    await ws.send(json.dumps(sub_msg))
                
                logger.info(f"Sent batch {i//50 + 1}. Waiting for responses...")
                
                # Listen for 2 seconds to capture confirmations or data
                end_time = datetime.now().timestamp() + 2
                while datetime.now().timestamp() < end_time:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        data = json.loads(msg)
                        if data.get("type") == "funding_rate" and "data" in data:
                            res = data["data"]
                            if "r" in res:
                                active.add(data.get("pairCode", "").upper())
                    except:
                        pass
            
            logger.info(f"Discovery Complete. Active symbols: {len(active)}")
            print(f"ACTIVE_SYMBOLS={json.dumps(list(active))}")

    except Exception as e:
        logger.error(f"Discovery failed: {e}")

if __name__ == "__main__":
    asyncio.run(discover())
