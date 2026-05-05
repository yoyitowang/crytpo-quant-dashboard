import urllib.request
import json

url = "https://api.coinw.com/api/v1/public?command=returnFundingRate&instrument=btc"
headers = {"User-Agent": "Mozilla/5.0"}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read().decode())
    print(json.dumps(d, indent=2))
