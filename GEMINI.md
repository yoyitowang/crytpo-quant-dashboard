# Crypto Funding Rate Project - Engineering Standards & Workflow

## 強制開發流程 (Mandatory Workflow)

每當接收到新需求時，必須嚴格遵守以下七個階段，不得跳過：

### 1. 需求釐清 (Requirements Clarification)
- **動作**：與使用者確認功能目標、數據定義與視覺要求。
- **目標**：驗證規格定義，消除歧義。在使用者確認前不進行代碼實作。

### 2. 任務盤點 (Task Inventory)
- **動作**：列出受影響的模組（如：後端 Collector、API 端點、前端 UI 組件、資料庫 Schema）。
- **目標**：評估技術可行性與潛在風險。

### 3. 任務拆分 (Task Breakdown)
- **動作**：將盤點的任務拆解為可執行的微小步驟（Sub-tasks）。
- **目標**：確保任務粒度適中，方便逐步驗證。

### 4. 任務執行 (Task Execution)
- **動作**：進行代碼編寫、重構或環境設定。
- **原則**：維持代碼風格一致性，必須考慮 Null 值處理與效能優化。

### 5. 規格驗證 (Specification Validation)
- **動作**：檢查實作結果是否符合第一階段定義的規格。
- **迴圈**：若不符合或產生 Bug，必須重回執行階段修正，直到完全正確為止。

### 6. 服務管理 (Service Management)
- **動作**：主動詢問使用者是否需要重啟服務（例如：`docker compose up --build -d`）。
- **目標**：確保環境與最新代碼同步。

### 7. 最後交付 (Final Delivery)
- **動作**：提交最終成果報告，包含修正重點與使用說明。

---

## 專案技術準則
- **效能優先**：資料庫必須使用分區表，即時數據優先走 Redis。
- **強健排序**：任何排序功能必須正確處理 Null 值（Null 永遠排在最後）。
- **UI 風格**：維持 "QuantMatrix" 專業暗色調、高對比熱力圖視覺。
