#!/usr/bin/env python3
import asyncio, time, sys, json, re
from datetime import datetime, timedelta, timezone
import aiohttp
import ccxt.async_support as ccxt_async

from backend.app.api.endpoints import get_history_from_db
from backend.app.dependencies import get_symbol_inventory, set_symbol_inventory
from backend.app.services.symbol_inventory import symbol_inventory

set_symbol_inventory(symbol_inventory)

async def time_fetch(label: str, coro):
    t0 = time.time()
    result = await coro
    t = time.time() - t0
    n = len(result) if isinstance(result, list) else 0
    return t, n, result

def print_fetch(label: str, coro):
    t0 = time.time()
    result = asyncio.get_event_loop().run_until_complete(coro)
    # Actually we use await in main()
    return result

async def fetch_coinw_history(symbol, days):
    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
    if not match: return []
    base = match.group(1).upper()
    quote = match.group(2).upper()
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://api.coinw.com/v1/perpum/fundingRate?symbol={base}_{quote}&limit=500"
            async with s.get(url, timeout=15) as r:
                if r.status == 200:
                    d = await r.json()
                    if isinstance(d, list):
                        since_ms = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
                        res = []
                        for i in d:
                            if i.get('fundingRate') is not None and i.get('fundingTime', 0) >= since_ms:
                                res.append({
                                    'timestamp': datetime.fromtimestamp(i['fundingTime']/1000, tz=timezone.utc).isoformat(),
                                    'rate': float(i['fundingRate'])
                                })
                        return sorted(res, key=lambda x: x['timestamp'])
    except Exception as e:
        pass
    return []

async def fetch_asterdex_history(symbol, days):
    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
    if not match: return []
    raw_sym = match.group(1).upper() + match.group(2).upper()
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://fapi.asterdex.com/fapi/v3/fundingRate?symbol={raw_sym}&limit=500"
            async with s.get(url, timeout=15) as r:
                if r.status == 200:
                    d = await r.json()
                    if isinstance(d, list):
                        res = []
                        for i in d:
                            if i.get('fundingRate') is not None:
                                res.append({
                                    'timestamp': datetime.fromtimestamp(i['fundingTime']/1000, tz=timezone.utc).isoformat(),
                                    'rate': float(i['fundingRate'])
                                })
                        return sorted(res, key=lambda x: x['timestamp'])
    except Exception as e:
        pass
    return []

async def fetch_ccxt_history(ex_id, symbol, days, use_cache=False):
    match = re.match(r'^(.*?)(USDT|USDC)$', symbol, re.IGNORECASE)
    if not match: return [], None
    base, quote = match.group(1).upper(), match.group(2).upper()
    ex = getattr(ccxt_async, ex_id)({'options': {'defaultType': 'swap'}, 'timeout': 15000})
    try:
        t_markets = 0.0
        if use_cache:
            si = get_symbol_inventory()
            cached = si.get_markets(ex_id) if si else None
            if cached:
                ex.markets = cached
            else:
                t0 = time.time()
                await ex.load_markets()
                t_markets = time.time() - t0
        else:
            t0 = time.time()
            await ex.load_markets()
            t_markets = time.time() - t0

        possible_syms = []
        if ex_id == 'okx':
            possible_syms = [f'{base}-{quote}-SWAP', f'{base}/{quote}:{quote}']
        elif ex_id == 'hyperliquid':
            possible_syms = [f'{base}/{quote}:{quote}']
        else:
            possible_syms = [f'{base}/{quote}:{quote}', f'{base}/{quote}', f'{base}{quote}']

        ccxt_sym = None
        for s in possible_syms:
            if s in ex.markets:
                ccxt_sym = s
                break
        if not ccxt_sym:
            for s, mkt in ex.markets.items():
                if mkt.get('swap') and mkt.get('base') == base and (mkt.get('quote') == quote or mkt.get('settle') == quote):
                    ccxt_sym = s
                    break

        if ccxt_sym and ex.has.get('fetchFundingRateHistory'):
            since_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
            t0 = time.time()
            hist = await ex.fetch_funding_rate_history(ccxt_sym, since=since_ms, limit=1000)
            t_fetch = time.time() - t0
            result = [{'timestamp': datetime.fromtimestamp(h['timestamp']/1000, tz=timezone.utc).isoformat(), 'rate': float(h['fundingRate'])} for h in hist if h.get('fundingRate') is not None]
            return result, {'markets': t_markets, 'fetch': t_fetch}
        return [], {'markets': t_markets, 'fetch': 0}
    finally:
        await ex.close()

async def main():
    results = {}

    print('=' * 80)
    print('PHASE 1: CUSTOM REST API EXCHANGES')
    print('=' * 80)

    print('\n--- COINW (REST API) ---')
    results['coinw'] = {}
    for sym in ['BTCUSDT', 'ETHUSDT']:
        results['coinw'][sym] = {}
        print(f'  [{sym}]')
        for days in [7, 14, 30]:
            t, n, _ = await time_fetch(f'    {days:>2}d', fetch_coinw_history(sym, days))
            results['coinw'][sym][days] = (t, n)

    print('\n--- ASTERDEX (REST API) ---')
    results['asterdex'] = {}
    for sym in ['BTCUSDT', 'ETHUSDT']:
        results['asterdex'][sym] = {}
        print(f'  [{sym}]')
        for days in [7, 14, 30]:
            t, n, _ = await time_fetch(f'    {days:>2}d', fetch_asterdex_history(sym, days))
            results['asterdex'][sym][days] = (t, n)

    print('\n--- LIGHTER ---')
    print('  Always returns empty [] — skipped')
    results['lighter'] = {'N/A': {7: (0, 0), 14: (0, 0), 30: (0, 0)}}

    print('\n--- ADEN (PostgreSQL DB) ---')
    results['aden'] = {}
    for sym in ['ETHUSDT', 'BTCUSDT', 'IRYSUSDT']:
        results['aden'][sym] = {}
        print(f'  [{sym}]')
        for days in [7, 14, 30]:
            t, n, _ = await time_fetch(f'    {days:>2}d', get_history_from_db('aden', sym, days))
            results['aden'][sym][days] = (t, n)

    print()
    print('=' * 80)
    print('PHASE 2: CCXT EXCHANGES — COLD START')
    print('=' * 80)

    CCXT_LIST = [
        ('binance', 'ETHUSDT'),
        ('bybit', 'ETHUSDT'),
        ('okx', 'ETHUSDT'),
        ('bitget', 'ETHUSDT'),
        ('gateio', 'ETHUSDT'),
        ('kucoin', 'ETHUSDT'),
        ('mexc', 'ETHUSDT'),
        ('bingx', 'ETHUSDT'),
        ('hyperliquid', 'ETHUSDT'),
    ]

    results['ccxt_cold'] = {}
    for ex_id, sym in CCXT_LIST:
        results['ccxt_cold'][ex_id] = {}
        results['ccxt_cold'][ex_id]['breakdown'] = {}
        print(f'\n  +++ {ex_id} / {sym} +++')
        for days in [7, 14, 30]:
            t0 = time.time()
            data, breakdown = await fetch_ccxt_history(ex_id, sym, days, use_cache=False)
            t = time.time() - t0
            n = len(data)
            results['ccxt_cold'][ex_id][days] = (t, n)
            results['ccxt_cold'][ex_id]['breakdown'][days] = breakdown
            lm = breakdown['markets'] if breakdown else 0
            fh = breakdown['fetch'] if breakdown else 0
            print(f'    {days:>2}d: total={t:.2f}s, n={n:>3d} entries (load_markets={lm:.2f}s, fetch_history={fh:.2f}s)')

    print()
    print('=' * 80)
    print('PHASE 3: CCXT EXCHANGES — WARM CACHE')
    print('=' * 80)

    results['ccxt_warm'] = {}
    for ex_id, sym in CCXT_LIST:
        results['ccxt_warm'][ex_id] = {}
        print(f'\n  +++ {ex_id} / {sym} +++')
        for days in [7, 14, 30]:
            t0 = time.time()
            data, breakdown = await fetch_ccxt_history(ex_id, sym, days, use_cache=True)
            t = time.time() - t0
            n = len(data)
            results['ccxt_warm'][ex_id][days] = (t, n)
            lm = breakdown['markets'] if breakdown else 0
            fh = breakdown['fetch'] if breakdown else 0
            print(f'    {days:>2}d: total={t:.2f}s, n={n:>3d} entries (load_markets={lm:.2f}s, fetch_history={fh:.2f}s)')

    print()
    print('=' * 80)
    print('SUMMARY TABLE')
    print('=' * 80)
    print(f'{"Exchange":<14} {"Source":<10} {"7d":<12} {"14d":<12} {"30d":<12} {"Entries(7d)":<12}')
    print('-' * 72)

    for ex_id in ['coinw', 'asterdex', 'aden', 'lighter']:
        r = results.get(ex_id, {})
        src = {'coinw': 'REST API', 'asterdex': 'REST API', 'aden': 'DB', 'lighter': 'N/A'}.get(ex_id, '?')
        sym_key = list(r.keys())[0] if r else None
        if sym_key:
            t7 = r[sym_key].get(7, (0,0))[0]
            t14 = r[sym_key].get(14, (0,0))[0]
            t30 = r[sym_key].get(30, (0,0))[0]
            n7 = r[sym_key].get(7, (0,0))[1]
            print(f'{ex_id:<14} {src:<10} {t7:<8.2f}s    {t14:<8.2f}s    {t30:<8.2f}s    {n7:<6}')
        else:
            print(f'{ex_id:<14} {src:<10} {"—":<12} {"—":<12} {"—":<12} {"—":<12}')

    print()
    print('--- CCXT Exchanges (Cold Start — includes load_markets) ---')
    print(f'{"Exchange":<14} {"Source":<10} {"7d":<12} {"14d":<12} {"30d":<12} {"load_mkts":<12}')
    print('-' * 72)
    for ex_id, _ in CCXT_LIST:
        r = results.get('ccxt_cold', {}).get(ex_id, {})
        b = r.get('breakdown', {})
        t7 = r.get(7, (0,0))[0]
        t14 = r.get(14, (0,0))[0]
        t30 = r.get(30, (0,0))[0]
        lm = b.get(7, {}).get('markets', 0) if b else 0
        print(f'{ex_id:<14} {"CCXT":<10} {t7:<8.2f}s    {t14:<8.2f}s    {t30:<8.2f}s    {lm:<.2f}s')

    print()
    print('--- CCXT Exchanges (Warm Cache — cached load_markets) ---')
    print(f'{"Exchange":<14} {"Source":<10} {"7d":<12} {"14d":<12} {"30d":<12} {"fetch_hist":<12}')
    print('-' * 72)
    for ex_id, _ in CCXT_LIST:
        r = results.get('ccxt_warm', {}).get(ex_id, {})
        b = results.get('ccxt_cold', {}).get(ex_id, {}).get('breakdown', {})
        t7 = r.get(7, (0,0))[0]
        t14 = r.get(14, (0,0))[0]
        t30 = r.get(30, (0,0))[0]
        fh = b.get(7, {}).get('fetch', 0) if b else 0
        print(f'{ex_id:<14} {"CCXT":<10} {t7:<8.2f}s    {t14:<8.2f}s    {t30:<8.2f}s    {fh:<.2f}s')

asyncio.run(main())
