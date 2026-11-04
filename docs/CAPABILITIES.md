# Codex 能力檢查紀錄

檢查日期：2026-11-04（Asia/Taipei）。這是當次環境觀察，不保證所有 Codex 客戶端與帳戶皆有相同能力。

## 已觀察與實測

| 項目 | 結果 | 證據／限制 |
|---|---|---|
| 儲存庫 | 初始為空，尚無 commit | 指向 `grapycalpis/agent-council`，GitHub 連接器回報可 push |
| Python | 系統 3.9.6；另有 3.12.14 | 實作與測試使用專案 `.venv` 的 3.12.14 |
| Codex CLI | `0.166.0-alpha.5.1` | 本機 `codex --version` 實測 |
| 非互動介面 | `exec`、`exec resume`、`--json`、`--output-schema` 出現在 help | 僅檢視 help，未執行付費／真實非互動推論，未宣稱 backend 已接上 |
| 聊天子代理建立 | 提供 `collaboration.spawn_agent` | 已用 `fork_turns=none` 建立 `/root/capability_probe` |
| 新上下文 | 第一輪不繼承父對話 | 子代理指出仍有系統／開發者／環境指示；不誇稱是完全無指示上下文 |
| 同代理續接 | `collaboration.followup_task` 成功 | 第二輪回憶原始代碼並看到自己的第一輪回答 |
| 並行 | 本會話共四個活躍槽位，含主代理 | 因此設定最多三個子代理並行，十二人須分批 |
| 模型／用量 | 探測工具未回傳可稽核的個別模型 ID 或 token 數 | 記錄為不可取得，不推測 |
| 完整十二人評估 | 尚未執行 | 只有一個兩輪能力探測；自動測試均不呼叫 LLM |

探測的兩輪輸入與原始回答見 [capability-probe.json](capability-probe.json)。它不是正式評估，也不會出現在十二人票數中。新上下文與續接已實測；這並不能證明共享檔案系統的 OS 隔離或模型偏誤獨立。

## 官方文件與專案設定

依查閱的 [OpenAI 官方子代理文件](https://learn.chatgpt.com/docs/agent-configuration/subagents)，專案級自訂代理使用 `.codex/agents/` 下的 standalone TOML，每份至少含 `name`、`description`、`developer_instructions`；代理繼承父層權限。文件也說明可由主代理協調新建與後續訊息。

本庫據此提供十五份 TOML，但本工作階段建立工具未提供自訂代理選擇欄位，亦未重載客戶端，因此只確認檔案契約與 TOML 語法，不宣稱已成功自動載入。實際執行可直接用新上下文及權威角色任務包。

不加入全域 `config.toml`，不覆寫使用者模型或權限。Python 的 `native` 後端是互動橋接，不能直接呼叫聊天內的工具。官方 [Agents API 多代理說明](https://developers.openai.com/api/docs/guides/agents-api/multi-agent) 是另一個需 API 設定的執行面，本版未引入或測試。

## 狀態用語

- **已實作**：程式與命令存在。
- **已測試**：可離線重播的自動測試通過；若是原生工具實測會另外明示。
- **原生聲明收件**：上下文與模型欄位由執行操作者提供，程式不認證服務端執行。
- **尚未驗證**：包含 TOML 自動載入、完整真實十二人評估、非互動 CLI 自動執行。
- **未實作**：API、跨模型與進階分析；不靜默替代。
