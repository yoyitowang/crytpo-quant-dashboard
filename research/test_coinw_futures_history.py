import aiohttp
import asyncio

async def main():
    url = "https://api.coinw.com/api/v1/futures/funding_rate/history?symbol=BTCUSDT"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            print(f"Response: {data}")

if __name__ == "__main__":
    asyncio.run(main())
