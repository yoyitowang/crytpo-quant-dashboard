# Crypto Funding Rate Project - Development Log

## 專案規格與功能追蹤表

| 版本 | 功能模組 | 詳細規格說明 | 狀態 | 導入日期 |
| :--- | :--- | :--- | :--- | :--- |
| v1.0 | 核心採集 (POC) | 實作 Binance WebSocket 抓取 BTC/ETH 費率。 | ✅ 已導入 | 2024-04-25 |
| v2.0 | 後端基礎建設 | 導入 FastAPI, SQLAlchemy, PostgreSQL, Docker。 | ✅ 已導入 | 2024-04-25 |
| v3.0 | 矩陣 UI 雛形 | 實作以幣種為行、交易所為列的初步表格。 | ✅ 已導入 | 2024-04-25 |
| v4.0 | 深度分析終端 | 導入點擊單元格彈出歷史 AreaChart 走勢圖、年化收益計算。 | ✅ 已導入 | 2024-04-25 |
| v5.0 | 專業交易功能 | 導入 8h 費率/年化 APR 一鍵切換、結算倒數計時、週期標籤。 | ✅ 已導入 | 2024-04-26 |
| v6.0 | 資料庫效能優化 | 實作 **PostgreSQL 時間分區表 (Partitioning)** 與 **Redis 快取**。 | ✅ 已導入 | 2024-04-26 |
| v7.0 | 儲存邏輯優化 | 實作 **嚴格變動偵測 (Strict Change Detection)**，費率不變不進 DB。 | ✅ 已導入 | 2024-04-26 |
| v8.0 | 智慧排序系統 | 修復 Null 值排序問題，確保無數據行永遠墊底（不論 ASC/DESC）。 | ✅ 已導入 | 2024-04-26 |
| v9.0 | 過濾引擎與擴張 | 新增 7 家交易所支援、動態列切換、Min Spread 門檻篩選。 | ✅ 已導入 | 2024-04-26 |
| v9.1 | 熱圖矩陣重構 | X 軸幣種、Y 軸交易所的高密度 Heatplot 模式。 | ✅ 已導入 | 2024-04-26 |
| **v9.2** | **全連線加固** | **修復新交易所無資料問題、強化 WebSocket 心跳機制。** | 🏗️ 進行中 | 2024-04-26 |

---

## 已導入功能詳細清單

### 1. 數據採集層 (Collector)
- [x] **Binance**: 全市場 WSS 監控。
- [x] **OKX**: 動態獲取 USDT-SWAP 列表並分批訂閱 (WSS)。
- [x] **Bybit**: 獲取 Linear 列表並訂閱熱門幣種 (WSS)。
- [x] **Bitget**: 實作 WSS 心跳機制與主流幣種監控。
- [x] **Gate.io**: 修正列表/字典混合解析邏輯。
- [x] **KuCoin**: 實作自動 REST 輪詢機制。
- [x] **HTX**: 預留 gzip 解壓接口。

### 2. 存儲與分析層 (Backend API)
- [x] **Redis Layer**: 儲存 `latest:*` 即時狀態，支撐高頻 UI 讀取。
- [x] **Postgres Partitioning**: 按 `timestamp` 進行分區，確保海量數據下查詢不掉速。
- [x] **Aggregation API**: 支持 24h, 3d, 7d 平均費率計算。
- [x] **CORS Support**: 全域跨網域存取支持。

### 3. 使用者介面 (Frontend)
- [x] **Matrix View**: 專業級 sticky 表格。
- [x] **Heatplot View**: X/Y 軸情緒矩陣，可水平滾動。
- [x] **Filter Panel**: 動態勾選交易所、APR 門檻過濾。
- [x] **Smart Sorting**: 解決 Null 數據干擾排序的問題。
- [x] **Pagination**: 支持 10, 25, 50, 100 行顯示。
