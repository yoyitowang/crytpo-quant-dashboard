import aiohttp
import asyncio

async def main():
    url = "https://104.18.21.243/v1/perpum/fundingRateHistory?instrument=btc&pageSize=20&pageNum=1"
    headers = {"Host": "api.futurescw.com", "User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, ssl=False) as resp:
                data = await resp.json()
                print(f"Response: {data}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
