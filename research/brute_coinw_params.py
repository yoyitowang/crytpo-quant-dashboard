import aiohttp
import asyncio

async def main():
    url = "https://api.coinw.com/v1/perpum/fundingRateHistory"
    params_to_try = [
        {"instrument": "btc"},
        {"symbol": "btc"},
        {"instrumentName": "btc"},
        {"pairCode": "btc"},
        {"base": "btc", "quote": "usdt"},
        {"id": "1"},
        {"instrumentId": "1"},
        {"indexId": "1"},
    ]
    async with aiohttp.ClientSession() as session:
        for p in params_to_try:
            # Add required pagination just in case
            p.update({"pageSize": 20, "pageNum": 1})
            async with session.get(url, params=p) as resp:
                data = await resp.json()
                print(f"Params: {p} -> Code: {data.get('code')}")
                if data.get('code') == 0:
                    print(f"SUCCESS! {data}")

if __name__ == "__main__":
    asyncio.run(main())
