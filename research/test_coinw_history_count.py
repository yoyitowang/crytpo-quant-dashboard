import aiohttp
import asyncio

async def main():
    url = "https://api.coinw.com/v1/perpum/fundingRate?instrument=btc&history=100"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            print(f"Response: {data}")

if __name__ == "__main__":
    asyncio.run(main())
