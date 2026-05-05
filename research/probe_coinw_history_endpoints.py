import aiohttp
import asyncio
import json
from datetime import datetime

async def probe(session, url):
    print(f"Probing {url}")
    try:
        async with session.get(url, timeout=5) as resp:
            data = await resp.json()
            if data.get('code') == 0 or data.get('data'):
                print(f"SUCCESS: {url}")
                print(f"Response: {str(data)[:200]}")
                return True
    except Exception as e:
        # print(f"Failed {url}: {e}")
        pass
    return False

async def main():
    base = "https://api.coinw.com"
    patterns = [
        "/v1/perpum/fundingRateHistory?instrument=btc",
        "/v1/perpum/funding_rate_history?instrument=btc",
        "/v1/perpum/historyFundingRate?instrument=btc",
        "/api/v1/perpum/fundingRateHistory?instrument=btc",
        "/api/v1/futures/market/funding_rate_history?symbol=BTC_USDT",
    ]
    
    async with aiohttp.ClientSession() as session:
        tasks = [probe(session, base + p) for p in patterns]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
