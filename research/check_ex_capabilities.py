import asyncio
import ccxt.async_support as ccxt
import json

async def check_exchanges():
    ex_list = ['binance', 'okx', 'bybit', 'bitget', 'gateio', 'kucoin', 'mexc', 'bingx']
    results = {}
    
    for ex_id in ex_list:
        try:
            ex_class = getattr(ccxt, ex_id)()
            results[ex_id] = {
                "fetchFundingRateHistory": ex_class.has.get('fetchFundingRateHistory', False),
                "fetchFundingInterval": ex_class.has.get('fetchFundingInterval', False), # Not standard, but some might have it
                "fetchFundingRate": ex_class.has.get('fetchFundingRate', False)
            }
            await ex_class.close()
        except Exception as e:
            results[ex_id] = {"error": str(e)}
            
    # Add CoinW manually as we know it's not in this CCXT version or has limited support
    results['coinw'] = {
        "fetchFundingRateHistory": False, # Confirmed by user
        "fetchFundingInterval": False,
        "fetchFundingRate": True
    }
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(check_exchanges())
