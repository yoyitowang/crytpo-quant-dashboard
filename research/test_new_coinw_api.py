import aiohttp
import asyncio
import json

async def test_api(instrument, days=7):
    url = "https://futuresapi.faefrdpenn.com/v1/futuresc/public/selectFundingRateHistory"
    payload = {"instrument": instrument, "day": days}
    headers = {"Content-Type": "application/json"}
    
    print(f"Testing {instrument} for {days} days...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Response: {json.dumps(data, indent=2)[:500]}...")
                    if data.get('code') == 0 and data.get('data'):
                        print(f"SUCCESS: Found {len(data['data'])} records for {instrument}")
                    else:
                        print(f"FAILED: {data.get('msg')}")
                else:
                    text = await resp.text()
                    print(f"Error Response: {text}")
        except Exception as e:
            print(f"Request Error: {e}")

async def main():
    # Test the provided instrument
    await test_api("OPN")
    # Test common instruments to find naming rules
    await test_api("BTC")
    await test_api("ETH", days=14)
    await test_api("SOL")
    await test_api("eth")

if __name__ == "__main__":
    asyncio.run(main())
