# 評估工作流程 V1.0

此流程由 Main Agent 使用 Codex 原生工具執行；Python 只用於維護測試。

## 狀態與資料

`INTAKE → PACKET_FROZEN → INDEPENDENT_REVIEW → ROUND_ONE_LOCKED →
VERIFICATION_OR_SKIP → SYNTHESIS → REPORTED`

每次評估使用新的 `request_id`。只在父代理對話記憶保留 packet、派發紀錄、
有效結果、失敗紀錄、鎖定結果與驗證結果，不建立共用結果檔。
初始化維護的測試證據可存入 `evals/results/`，一般評估不得如此操作。

Neutral Review Packet 遵循 `schemas/review_packet.schema.json`：

- 原始問題逐字保留為資料；中立問題、目標、限制與假設分開列出。
- 已知事實各有 ID 及來源，例如 `user:原始敘述`，不把使用者主張當成已獨立驗證。
- 方案包含穩定 ID、內容及是否為維持現狀。若基準不適用，說明原因。
- 單方案模式仍可列基準，但投票只針對 `primary_option_id`；多方案使用比較票。
- 明訂 A08 專業與所有評審共用的評估重點，不預設任何結論。
- 每位角色的等待預算預設 180 秒，允許按任務在派發前設定 30–900 秒。
  這是流程預算，不是 Codex TOML 設定。等待工具每次最多阻塞 60 秒，並保持進度回報。

封包凍結後不得因先收到某些票就修改。新資訊若會影響比較公平性，結束此輪並
以新 request_id 重跑，舊結果仍標示已鎖定，不與新票混算。

## 類型與重點

| 類型 | 優先檢查 |
| --- | --- |
| Idea Evaluation | 價值、需求假設、可逆實驗 |
| Feasibility Assessment | 依賴、資源、能力、時程 |
| Decision Analysis | 目標、條件、機會成本、基準 |
| Option Comparison | 相同準則、同樣證據、維持現狀、不可比較處 |
| Technical Architecture Review | 相容性、失敗模式、維護、遷移與回復 |
| Risk Assessment | 風險來源、嚴重度、不可逆性、緩解 |
| Open-ended Exploration | 問題重述、選項空間、未知與小型探索 |

## 排程、截止與恢復

預定 A01–A08 八個獨立評審；並行上限取「8 與宿主可用槽位」較小者。
容量不足只排隊，不算評審失敗；不得為了湊八位而複用子代理上下文。
先派發所有可容納的角色，完成並回收槽位後繼續下一批，未派發者不開始計時。
已完成的回覆先驗證但不做跨評審整合，直到全部提交或確定失敗。

每個角色最多兩次嘗試（初次加一次重試）。分別記錄原生代理識別、時間、
attempt、狀態 `submitted / spawn_failed / invalid_output / timed_out`。
等待逾期先查看是否已完成，再中止該次嘗試。格式修正可由原子代理只重送其
JSON；若啟動新代理，仍只傳相同 packet、角色和格式錯誤，不能加結論提示。
重試逾期或失敗後，保留其他有效結果並繼續，無需要求使用者操作。
父代理不得替缺席角色填寫票；外部服務失效或取消要在稽核中保留。

每個有效結果都需核對 request_id、agent_id、角色、方案 ID、排名涵蓋、
evidence/risk 參照及所有分數理由。成功接受後立即不可變；在 ROUND_ONE_LOCKED
以完整有效集合做統計，等待中或超時的回覆不得偷偷加入已公布票數。

## 原生工具適配

工具介面以當次實際描述為準，不將工具名稱假定為設定鍵。
有自訂 agent 選擇器時，指定 `.codex/agents/` 的 `name`；僅有通用
`collaboration.spawn_agent` 時，以 `fork_turns="none"` 建立獨立 context，
把角色 TOML 的完整 developer_instructions 與 Schema 放入任務，或明確指定
只能讀自己的角色檔、凍結封包及輸出 Schema；不繼承歷史。
採用此適配要明示，不能宣稱宿主自動載入自訂角色或套用了其推理強度。
本 repo 不提供自己實作的 orchestrator、不另開付費 API，也不模擬代理。
