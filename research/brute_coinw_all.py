import aiohttp
import asyncio

async def probe(session, url):
    try:
        async with session.get(url, timeout=5) as resp:
            data = await resp.json()
            if data.get('code') == 0:
                print(f"SUCCESS: {url} -> {str(data)[:200]}")
                return True
    except:
        pass
    return False

async def main():
    base = "https://api.coinw.com"
    variations = [
        "/v1/perpum/fundingRateHistory?instrument=btc&pageSize=20&pageNum=1",
        "/v1/perpum/fundingRateHistory?instrument=btc&size=20&current=1",
        "/v1/perpum/fundingRateHistory?instrument=btc&limit=20&offset=0",
        "/v1/perpum/fundingRateHistory?instrument=btc&count=20",
        "/v1/perpum/fundingRateHistory?symbol=btc&pageSize=20&pageNum=1",
        "/v1/perpum/fundingRateHistory?symbol=BTCUSDT&pageSize=20&pageNum=1",
        "/v1/perpum/fundingRateHistory?instrument=BTCUSDT&pageSize=20&pageNum=1",
        "/v1/perpum/fundingRateHistory?instrument=btc_usdt&pageSize=20&pageNum=1",
        "/v1/perpum/fundingRateHistory?instrument=BTC_USDT&pageSize=20&pageNum=1",
        "/v1/perpum/fundingRateHistory?base=btc&quote=usdt&pageSize=20&pageNum=1",
        "/api/v1/public?command=returnFundingHistory&symbol=BTC_USDT",
        "/api/v1/public?command=returnFundingRateHistory&symbol=BTC_USDT",
        "/v1/perpum/fundingRate?instrument=btc&history=1",
        "/v1/perpum/fundingRate?instrument=btc&limit=100",
    ]
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[probe(session, base + v) for v in variations])

if __name__ == "__main__":
    asyncio.run(main())
