import aiohttp
import asyncio

async def main():
    subs = ["api", "fapi", "futures-api", "perp-api"]
    path = "/v1/perpum/fundingRateHistory?instrument=btc&pageSize=20&pageNum=1"
    async with aiohttp.ClientSession() as session:
        for sub in subs:
            url = f"https://{sub}.coinw.com{path}"
            try:
                async with session.get(url, timeout=5) as resp:
                    print(f"URL: {url} -> Status: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"Data: {data}")
            except:
                pass

if __name__ == "__main__":
    asyncio.run(main())
