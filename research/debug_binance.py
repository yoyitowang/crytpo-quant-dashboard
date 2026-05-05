import asyncio
import ccxt.async_support as ccxt

async def main():
    ex = ccxt.binance()
    await ex.load_markets()
    print(f"Has: {ex.has.get('fetchFundingRateHistory')}")
    print(f"BTC/USDT:USDT in: {'BTC/USDT:USDT' in ex.markets}")
    hist = await ex.fetch_funding_rate_history('BTC/USDT:USDT', limit=5)
    print(f"Records: {len(hist)}")
    await ex.close()

if __name__ == "__main__":
    asyncio.run(main())
