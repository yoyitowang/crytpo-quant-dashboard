import aiohttp
import asyncio
import json

async def check_binance(session):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with session.get(url) as resp:
        data = await resp.json()
        sample = data['symbols'][0]
        print(f"Binance Sample: {sample['symbol']} - fundingIntervalHours: {sample.get('fundingIntervalHours')}")

async def check_okx(session):
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    async with session.get(url) as resp:
        data = await resp.json()
        sample = data['data'][0]
        # In OKX, funding interval is not directly in instruments, but in funding-rate
        print(f"OKX Sample: {sample['instId']}")
        # Need to check funding-rate for interval
        fr_url = f"https://www.okx.com/api/v5/public/funding-rate?instId={sample['instId']}"
        async with session.get(fr_url) as fr_resp:
            fr_data = await fr_resp.json()
            if fr_data.get('data'):
                print(f"OKX Funding Rate Sample: {fr_data['data'][0]}")

async def check_bybit(session):
    url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
    async with session.get(url) as resp:
        data = await resp.json()
        sample = data['result']['list'][0]
        print(f"Bybit Sample: {sample['symbol']} - fundingInterval: {sample.get('fundingInterval')}")

async def check_gate(session):
    url = "https://api.gateio.ws/api/v4/futures/usdt/contracts"
    async with session.get(url) as resp:
        data = await resp.json()
        sample = data[0]
        print(f"Gate Sample: {sample['name']} - funding_interval: {sample.get('funding_interval')}")

async def main():
    async with aiohttp.ClientSession() as session:
        await check_binance(session)
        await check_okx(session)
        await check_bybit(session)
        await check_gate(session)

if __name__ == "__main__":
    asyncio.run(main())
