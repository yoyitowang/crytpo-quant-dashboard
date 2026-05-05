import asyncio
import ccxt.async_support as ccxt
import re

async def test_ex(ex_id, symbol):
    print(f"Testing {ex_id} for {symbol}...")
    try:
        ex = getattr(ccxt, ex_id)()
        match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
        base, quote = (match.group(1).upper(), match.group(2).upper()) if match else (symbol.upper(), 'USDT')
        
        if ex_id == 'okx':
            ccxt_sym = f"{base}-{quote}-SWAP"
        elif ex_id == 'binance':
            ccxt_sym = f"{base}/{quote}:{quote}"
        elif ex_id == 'bybit' or ex_id == 'bitget' or ex_id == 'mexc' or ex_id == 'gateio':
            ccxt_sym = f"{base}/{quote}:{quote}"
        else:
            ccxt_sym = f"{base}/{quote}"
            
        print(f"  CCXT Symbol: {ccxt_sym}")
        await ex.load_markets()
        print(f"  Has fetchFundingRateHistory: {ex.has.get('fetchFundingRateHistory')}")
        if ex.has.get('fetchFundingRateHistory'):
            hist = await ex.fetch_funding_rate_history(ccxt_sym, limit=5)
            print(f"  SUCCESS: Found {len(hist)} records.")
        await ex.close()
    except Exception as e:
        print(f"  FAILED: {e}")
        try: await ex.close()
        except: pass

async def main():
    exchanges = ['binance', 'okx', 'bybit', 'bitget', 'gateio', 'mexc']
    for ex in exchanges:
        await test_ex(ex, "BTCUSDT")

if __name__ == "__main__":
    asyncio.run(main())
