import urllib.request
import json

commands = [
    "returnFundingRateHistory", 
    "fundingRateHistory", 
    "getFundingRateHistory", 
    "fundingHistory",
    "returnFundingRate",
    "fundingRate"
]
symbol = "BTC-USDT"
headers = {"User-Agent": "Mozilla/5.0"}

for cmd in commands:
    url = f"https://api.coinw.com/api/v1/public?command={cmd}&symbol={symbol}"
    print(f"--- Probing {cmd} for {symbol} ---")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read().decode())
            print(f"Keys: {list(d.keys())}")
            if d.get('data'):
                print(f"Data: {str(d['data'])[:200]}")
            else:
                print("Data is empty")
    except Exception as e:
        print(f"Failed: {e}")

# Try another possible base URL
for cmd in commands:
    url = f"https://api.futurescw.com/api/v1/public?command={cmd}&symbol={symbol}"
    print(f"--- Probing {cmd} on futurescw for {symbol} ---")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read().decode())
            print(f"Keys: {list(d.keys())}")
            if d.get('data'):
                print(f"Data: {str(d['data'])[:200]}")
    except Exception as e:
        print(f"Failed: {e}")
