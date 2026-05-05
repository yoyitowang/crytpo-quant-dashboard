import asyncio
import ccxt.async_support as ccxt
import json

async def main():
    ex = ccxt.coinw()
    print(f"CoinW has fetchFundingRateHistory: {ex.has.get('fetchFundingRateHistory')}")
    if ex.has.get('fetchFundingRateHistory'):
        try:
            markets = await ex.load_markets()
            # Find a USDT swap market
            symbol = None
            for s, m in markets.items():
                if m.get('swap') and m.get('settle') == 'USDT':
                    symbol = s
                    break
            
            if symbol:
                print(f"Fetching history for {symbol}...")
                history = await ex.fetch_funding_rate_history(symbol)
                print(f"History sample: {history[:2]}")
            else:
                print("No USDT swap market found.")
        except Exception as e:
            print(f"Error: {e}")
    await ex.close()

if __name__ == "__main__":
    asyncio.run(main())
