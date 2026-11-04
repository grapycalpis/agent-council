# 初始化驗證紀錄

日期：2026-11-04（Asia/Taipei）。本機：macOS、Python 3.9.6、
`codex-cli 0.166.0-alpha.6`。測試依賴只裝入 `/tmp/perspective-council-qa-venv`。
未更動全域 Codex 設定、登入、模型、信任或系統 Python，未 Commit／Push。

## 靜態與原生解析

| 驗證 | 結果 | 證據 |
| --- | --- | --- |
| TOML、結構與必要指令 | PASS | validate.py：10 份代理 TOML、根設定、4 份 packet |
| JSON Schema 語法 | PASS | jsonschema Draft202012Validator.check_schema，3 份 Schema |
| Schema 與跨欄位行為 | PASS | 39 項 unittest，包含全部四類封包與八位身份 |
| `[agents]` 支援鍵與權限鍵 | PASS | 本機 `--strict-config app-server --print-startup-config` |
| strict parser 確實生效 | PASS | 故意加入不存在設定鍵的負向控制被拒絕 |
| 角色推理與指令設定層 | PASS | 10 份 model_reasoning_effort / developer_instructions 原生解析接受 |
| AGENTS.md 原生探索 | PASS | `codex debug prompt-input` 的模型輸入含專案規範 |
| 獨立角色檔原生探索 | PASS | 原生 spawn 的 agent_type 描述列出全部 10 個自訂角色及推理強度 |

最初的套件下載受 sandbox 網路限制，透過正式權限核准後完成至 /tmp。
prompt-input 最初受到本機 runtime 權限限制，授權後唯讀診斷成功。
完整 prompt 只存 /tmp，不放入 Repository，避免包含使用者的全域設定。
本機 `codex debug` 不支援 `--strict-config`，因此 strict 設定檢查與 debug 探索
分開執行，未把不支援參數當成有效測試。

實際重跑命令：

```sh
/tmp/perspective-council-qa-venv/bin/python evals/validate.py
/tmp/perspective-council-qa-venv/bin/python -m unittest discover -s evals -p 'test_*.py' -v
/tmp/perspective-council-qa-venv/bin/python evals/check_codex.py \
  --prompt-input-json /tmp/perspective-council-prompt-input.json
/tmp/perspective-council-qa-venv/bin/python evals/check_smoke.py
```

`check_codex.py` 的診斷摘要不回顯完整使用者 prompt；原生工具描述中的
角色定義才算探索證據，單純在 AGENTS.md 出現角色名稱不算。

## 真正多代理 Smoke Test

**已實際委派並回收**：A01 Advocate、A03 Risk Analyst、A08 Domain Specialist，
三個全新 context，均 `fork_turns="none"`，使用同一中立封包。
收齊並以 Schema／語意檢查後鎖票，再獨立派 V02 Risk Auditor。

| 項目 | 結果 |
| --- | --- |
| 實際第一輪 | 3/3 有效，全部 OPPOSE，無格式修復、重試或失敗 |
| 真實原生識別 | /root/smoke_a01、/root/smoke_a03、/root/smoke_a08 |
| 動態領域 | Database Reliability and Disaster Recovery Engineer |
| 第二輪 | /root/smoke_v02；因重大風險及 high_stakes 觸發 |
| 驗證結果 | C01 CONFIRMED、C02 CONFIRMED、C03 UNRESOLVED |
| 原始結果保存 | smoke/A01.json、A03.json、A08.json、V02.json，僅 JSON 序列化排版整理 |
| 票數不可變 | round_one.lock.json 在驗證後重新計算相同 canonical SHA-256 |
| 報告 | smoke/report.md，完整九節繁體中文與限制 |

宿主提供 4 個活動槽位含主代理，本次採縮小 3 位評審的維護測試。
這是實際的多 context 原生派發，沒有 Main Agent 代寫缺席角色。
本對話的 collaboration 介面不能指定原生自訂 agent_type，因此子代理被明確
要求讀取自己的完整角色指令與 Schema；自訂角色探索成功與本次通用派發
分別記錄，不混為「已透過自訂選角器執行」。

## 尚未動態驗證與已知限制

- 八位完整評審及八位同時並行，尚未實測；設定上限 8 不會突破宿主限制。
- 新對話中只輸入自然語言即自動完成完整八人流程，尚未做模型端到端測試；
  已證明 AGENTS.md 與角色探索載入，路由規範已建立。首次使用需新對話載入。
- 以原生自訂角色選擇器完成實際派發，尚未測；本次使用通用原生工具適配。
- 原生啟動失敗、逾期、格式修復與重試、較低容量分批等故障分支，尚未全部注入。
  合成契約測試涵蓋無效回覆拒絕、缺席計票、重複角色拒絕等資料行為，不冒充
  原生排程或恢復測試。
- 無需驗證的跳過路徑與多方案排名已做合成契約測試，尚未另跑原生多代理情境。
- 外部網路查證、真實資料庫盤點、提示注入抵抗與工具級隔離未做動態認證。
- 本次觀察到的是派發參數與回傳內容，不是子代理內部完整工具 trace 的獨立證明。
  本 repo 不提供工作區或工具權限強制隔離，模型偏誤也可能相關。
- Python 的機械式驗證僅維護工具；一般評估若不能執行，按相同契約人工檢查並
  如實揭露。沒有外部執行期 Orchestrator、資料庫或模型 API 費用依賴。

已完成 V1.0 初始化的必要檔案、可行靜態／原生解析與縮小動態測試，
以上未驗證能力不包含在此次動態通過範圍。
