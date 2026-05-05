import asyncio
import ccxt.async_support as ccxt
import re

async def test_ex(ex_id, symbol):
    print(f"Testing {ex_id} for {symbol}...")
    try:
        ex = getattr(ccxt, ex_id)()
        match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
        ccxt_sym = f"{match.group(1)}/{match.group(2)}:USDT" if match else symbol
        
        # Specific overrides for exchanges known to be picky
        if ex_id == 'binance':
            ccxt_sym = f"{match.group(1)}/{match.group(2)}:USDT" if match else symbol
        elif ex_id == 'okx':
            ccxt_sym = f"{match.group(1)}-{match.group(2)}-SWAP"
        elif ex_id == 'gateio':
            ccxt_sym = f"{match.group(1)}_{match.group(2)}"
            # Gate might need explicit market finding
            markets = await ex.load_markets()
            found = [s for s, m in markets.items() if m.get('swap') and (s == ccxt_sym or m.get('id') == ccxt_sym)]
            if found: ccxt_sym = found[0]
            
        print(f"  CCXT Symbol: {ccxt_sym}")
        # Need to load markets first for some
        await ex.load_markets()
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
