import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0"}
symbol = "BTC_USDT"

# Possible commands based on typical patterns
commands = [
    "returnFundingRateHistory", 
    "fundingRateHistory", 
    "getFundingRateHistory", 
    "fundingHistory",
    "getFundingHistory"
]

for cmd in commands:
    url = f"https://api.coinw.com/api/v1/public?command={cmd}&symbol={symbol}"
    print(f"Trying {url}")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            print(f"Result: {d.get('code')}, Msg: {d.get('msg')}")
            if d.get('data'): print("DATA FOUND!")
    except: pass

# Try the direct path style again but with /v1/
paths = [
    "/api/v1/futures/market/funding_rate_history",
    "/v1/futures/market/funding_rate_history",
    "/api/v1/perpum/funding_rate_history",
    "/v1/perpum/fundingRateHistory"
]

for path in paths:
    url = f"https://api.coinw.com{path}?symbol={symbol}"
    print(f"Trying {url}")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            print(f"Result: {d.get('code')}")
    except: pass
