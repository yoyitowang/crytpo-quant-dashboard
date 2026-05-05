import urllib.request
import json

commands = ["returnFundingHistory", "fundingHistory", "getFundingRateHistory", "funding_rate_history"]
headers = {"User-Agent": "Mozilla/5.0"}
params = ["symbol=BTC_USDT", "instrument=btc", "pairCode=BTC"]

for cmd in commands:
    for p in params:
        url = f"https://api.coinw.com/api/v1/public?command={cmd}&{p}&limit=100"
        print(f"Trying {url}")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                d = json.loads(r.read().decode())
                if d.get('data') or d.get('code') == 200:
                    print(f"SUCCESS: {d.get('code')} - Data len: {len(d.get('data', []))}")
                    if d.get('data'): print(f"Sample: {str(d['data'])[:100]}")
        except: pass
