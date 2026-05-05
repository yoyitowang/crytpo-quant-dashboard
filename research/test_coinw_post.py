import aiohttp
import asyncio

async def main():
    url = "https://api.coinw.com/v1/perpum/fundingRateHistory"
    params = {"instrument": "btc", "pageSize": 20, "pageNum": 1}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=params) as resp:
            data = await resp.json()
            print(f"POST Response: {data}")
        async with session.post(url, json=params) as resp:
            data = await resp.json()
            print(f"POST JSON Response: {data}")

if __name__ == "__main__":
    asyncio.run(main())
