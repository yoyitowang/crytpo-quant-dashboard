import aiohttp
import asyncio

async def main():
    url = "https://api.coinw.com/v1/perpum/fundingRateHistory?base=btc&quote=usdt&pageSize=20&pageNum=1"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            print(f"Response with base/quote: {data}")

if __name__ == "__main__":
    asyncio.run(main())
