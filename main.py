import asyncio
import websockets
import json
from datetime import datetime

# 幣安 U本位合約全市場標記價格頻道
BINANCE_FUTURES_WSS_URL = "wss://fstream.binance.com/ws/!markPrice@arr"

async def binance_funding_rate_stream():
    """建立 WebSocket 連線並持續接收全市場資金費率"""
    
    while True: # 外層迴圈：負責斷線重連
        try:
            print(f"[{datetime.now()}] 正在連線至幣安 WebSocket...")
            async with websockets.connect(BINANCE_FUTURES_WSS_URL) as websocket:
                print("✅ 連線成功！開始接收資料...")
                
                while True: # 內層迴圈：負責持續接收訊息
                    message = await websocket.recv()
                    data = json.loads(message)
                    print(len(data), "筆資料接收成功！")
                    
                    # data 是一個陣列，包含所有幣種的資訊
                    # 這裡示範擷取 BTCUSDT 和 ETHUSDT 作為檢查
                    for item in data:
                        symbol = item['s']       # 交易對 (Symbol)
                        funding_rate = item['r'] # 資金費率 (Funding Rate)
                        next_time = item['T']    # 下次結算時間戳 (Next Funding Time)
                        
                        # 為了畫面簡潔，我們只印出 BTC 和 ETH，但實際上你已經拿到了幾百個幣種的資料
                        if symbol in ['BTCUSDT', 'ETHUSDT']:
                            # 將毫秒時間戳轉換為可讀時間
                            dt_object = datetime.fromtimestamp(next_time / 1000)
                            print(f"{symbol} | 費率: {float(funding_rate):.6f} | 下次結算: {dt_object}")
                            
        except websockets.ConnectionClosed as e:
            print(f"⚠️ 連線中斷: {e}。將在 5 秒後嘗試重新連線...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ 發生未預期的錯誤: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(binance_funding_rate_stream())
    except KeyboardInterrupt:
        print("\n程式已手動終止。")