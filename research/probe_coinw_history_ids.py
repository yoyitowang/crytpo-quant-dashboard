import aiohttp
import asyncio

async def main():
    paths = [
        "/v1/perpum/fundingRateHistory?instrumentId=1",
        "/v1/perpum/fundingRateHistory?id=1",
        "/v1/perpum/fundingRateHistory?base=btc&quote=usdt",
        "/v1/perpum/fundingRateHistory?symbol=btc_usdt",
        "/v1/perpum/fundingRateHistory?pairCode=btc",
    ]
    async with aiohttp.ClientSession() as session:
        for p in paths:
            url = f"https://api.coinw.com{p}"
            async with session.get(url) as resp:
                data = await resp.json()
                print(f"Path: {p} -> Response: {data}")

if __name__ == "__main__":
    asyncio.run(main())
