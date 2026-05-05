import aiohttp
import asyncio

async def main():
    paths = [
        "/v1/perpum/fundingRates?instrument=btc",
        "/v1/perpum/funding_rates?instrument=btc",
        "/v1/perpum/historyFundingRates?instrument=btc",
    ]
    async with aiohttp.ClientSession() as session:
        for p in paths:
            url = f"https://api.coinw.com{p}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Path: {p} -> Response: {data}")

if __name__ == "__main__":
    asyncio.run(main())
