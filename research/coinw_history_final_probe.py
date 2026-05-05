import urllib.request
import json

base_urls = ["https://api.coinw.com", "https://api.futurescw.com"]
symbols = ["BTC_USDT", "BTCUSDT", "btc_usdt"]
headers = {"User-Agent": "Mozilla/5.0"}

for base in base_urls:
    for sym in symbols:
        url = f"{base}/api/v1/futures/market/funding_rate_history?symbol={sym}"
        print(f"--- Probing {url} ---")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                d = r.read().decode()
                print(f"Success! Response: {d[:200]}")
        except Exception as e:
            print(f"Failed: {e}")
