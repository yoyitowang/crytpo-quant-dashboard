import asyncio
import json
import websockets
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CHIP-Test")

async def test_chip():
    url = "wss://ws.futurescw.com/perpum"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with websockets.connect(url, extra_headers=headers) as ws:
        # Try both common formats
        symbols = ["CHIP"] 
        for p in symbols:
            sub_msg = {"event": "sub", "params": {"biz": "futures", "type": "funding_rate", "pairCode": p}}
            await ws.send(json.dumps(sub_msg))
            logger.info(f"Sent Sub: {p}")

        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                logger.info(f"Received: {json.dumps(data, indent=2)}")
        except asyncio.TimeoutError:
            logger.info("Done waiting.")

if __name__ == "__main__":
    asyncio.run(test_chip())
