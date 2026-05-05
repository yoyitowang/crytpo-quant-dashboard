import aiohttp
import asyncio

async def probe(session, path):
    url = f"https://api.coinw.com{path}"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"SUCCESS: {path} -> {str(data)[:200]}")
                return True
            else:
                # print(f"Status {resp.status} for {path}")
                pass
    except:
        pass
    return False

async def main():
    paths = [
        "/v1/perpum/fundingRateHistory?instrument=btc",
        "/v1/perpum/fundingRateList?instrument=btc",
        "/v1/perpum/historyFundingRate?instrument=btc",
        "/v1/perpum/fundingHistory?instrument=btc",
        "/v1/perpum/funding_history?instrument=btc",
        "/v1/perpum/funding-history?instrument=btc",
        "/v1/perpum/fundingRate?instrument=btc&history=1",
        "/v1/perpum/fundingRate?instrument=btc&limit=100",
    ]
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[probe(session, p) for p in paths])

if __name__ == "__main__":
    asyncio.run(main())
