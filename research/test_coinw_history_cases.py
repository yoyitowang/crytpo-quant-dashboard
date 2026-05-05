import aiohttp
import asyncio

async def main():
    async with aiohttp.ClientSession() as session:
        for inst in ["btc", "BTC", "BTCUSDT", "BTC_USDT"]:
            url = f"https://api.coinw.com/v1/perpum/fundingRateHistory?instrument={inst}&pageSize=20&pageNum=1"
            async with session.get(url) as resp:
                data = await resp.json()
                print(f"Inst: {inst} -> Response: {data}")

if __name__ == "__main__":
    asyncio.run(main())
