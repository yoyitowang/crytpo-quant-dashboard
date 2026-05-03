import urllib.request
import json

commands = ["returnTicker", "returnSymbolMarket", "returnCurrencies", "returnFundingRate"]
headers = {"User-Agent": "Mozilla/5.0"}

for cmd in commands:
    url = f"https://api.coinw.com/api/v1/public?command={cmd}"
    print(f"--- Probing {cmd} ---")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read().decode())
            print(f"Keys: {list(d.keys())}")
            data = d.get('data')
            if data:
                print(f"Data Sample: {str(data)[:200]}")
                if "CHIP" in str(data):
                    print(f"!!! FOUND CHIP IN {cmd} !!!")
            else:
                print("Data is empty/None")
    except Exception as e:
        print(f"Failed: {e}")
