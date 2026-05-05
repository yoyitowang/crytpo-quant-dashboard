import urllib.request
import json

base_urls = ["https://api.coinw.com", "https://fapi.coinw.com"]
endpoints = ["/v1/perpum/fundingRateHistory", "/v1/perpum/fundingHistory", "/v1/perpum/fundingRates"]
instruments = ["btc", "BTC-USDT", "BTCUSDT"]
headers = {"User-Agent": "Mozilla/5.0"}

for base in base_urls:
    for ep in endpoints:
        for ins in instruments:
            url = f"{base}{ep}?instrument={ins}"
            print(f"--- Probing {url} ---")
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as r:
                    d = json.loads(r.read().decode())
                    print(f"Status: {d.get('code')}, Data: {str(d.get('data'))[:100]}")
            except Exception as e:
                print(f"Failed: {e}")

# Try command style again with instrument
commands = ["returnFundingRateHistory", "returnFundingRate"]
for cmd in commands:
    url = f"https://api.coinw.com/api/v1/public?command={cmd}&instrument=btc"
    print(f"--- Probing {url} ---")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            print(f"Keys: {list(d.keys())}")
    except Exception as e:
        print(f"Failed: {e}")
