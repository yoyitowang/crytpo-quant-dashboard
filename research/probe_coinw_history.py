import urllib.request
import json
import time

base_url = "https://api.coinw.com/v1/perpum/"
endpoints = [
    "fundingRateHistory",
    "fundingRates",
    "fundingHistory",
    "historicalFunding",
    "funding-rate-history"
]
instruments = ["btc", "BTC"]
headers = {"User-Agent": "Mozilla/5.0"}

for ep in endpoints:
    for ins in instruments:
        url = f"{base_url}{ep}?instrument={ins}&limit=100"
        print(f"--- Probing {url} ---")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                content = r.read().decode()
                try:
                    d = json.loads(content)
                    print(f"Code: {d.get('code')}, Msg: {d.get('msg')}, Data Type: {type(d.get('data'))}")
                    if d.get('data'):
                        print(f"Data Sample: {str(d['data'])[:500]}")
                        if isinstance(d.get('data'), list) and len(d.get('data')) > 0:
                            print(f"SUCCESS! Found {len(d['data'])} historical records.")
                except:
                    print(f"Not JSON. Content: {content[:200]}")
        except Exception as e:
            print(f"Failed: {e}")
        time.sleep(0.5)
