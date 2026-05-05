import aiohttp
import asyncio

async def probe(session, url):
    try:
        async with session.get(url, timeout=5) as resp:
            print(f"URL: {url} -> Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"Data: {str(data)[:200]}")
                if data.get('code') == 0 or data.get('data'):
                    return True
    except:
        pass
    return False

async def main():
    base = "https://api.coinw.com"
    variations = [
        "/api/v1/futures/funding_rate_history?symbol=BTC_USDT",
        "/api/v1/futures/funding_rate_history?instrument=btc",
        "/api/v1/futures/funding_rate_history?pairCode=btc",
        "/v1/perpum/market/funding_rate_history?instrument=btc",
        "/v1/perpum/market/fundingRateHistory?instrument=btc",
        "/v1/perpum/public/fundingRateHistory?instrument=btc",
    ]
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[probe(session, base + v) for v in variations])

if __name__ == "__main__":
    asyncio.run(main())
