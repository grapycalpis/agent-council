# 第一次真實十二人原生評估

本流程由互動 Codex 的主代理實際操作子代理工具，Python 負責固定的階段、驗證、計票與保存。沒有付費 API 金鑰需求；使用 Codex 本身仍受帳戶用量與可用工具限制。

## 操作起點

從專案根目錄啟用環境並建立評估：

```bash
source .venv/bin/activate
python -m agent_council validate
python -m agent_council run ideas/examples/example.yaml --backend native
python -m agent_council native prompt <評估ID>
```

把最後一個命令的輸出貼到同專案的 Codex 聊天，要求「使用真實獨立子代理完成這個評估」。不能只說「扮演十二位專家」。若客戶端沒有建立獨立上下文的工具，停留在待辦並記錄不支援；不能冒稱完成。

## 主代理執行規則

1. 讀取 `snapshot.json` 的 `max_concurrency`，再執行 `native tasks <評估ID>`。本次探測可用四個活躍代理槽位（含主代理），因此至多三個子代理並行；依實際空位分批。
2. 主代理讀取單一 `tasks/<任務ID>.json` 的完整內容。初次建立使用 `spawn_agent` 的 `fork_turns="none"` 或客戶端等效的全新上下文機制，只把該 JSON 直接嵌入任務訊息。禁止把父對話、其他評估或整個目錄傳入。
3. 陪審與辯論子代理不得呼叫工具、讀檔或看其他對話，只回傳符合 `output_schema` 的 JSON。它們仍會收到系統與開發者指示；這不是完全空白的模型上下文。
4. 等候工具的實際結果。保存工具實際回傳的 ID；不要自己發明十二個識別 ID。把原始 JSON 存到暫存檔，不更改投票、理由或 `changed`。
5. 使用下列收件命令；`--model` 與 `--token-usage` 僅在執行工具確實提供時填入，否則省略。

```bash
python -m agent_council native submit <評估ID> initial.software_engineer /tmp/engineer.json --context-id <實際代理ID>
```

6. 本階段全部收件或記錄失敗後推進：

```bash
python -m agent_council native advance <評估ID>
python -m agent_council native tasks <評估ID>
```

程式先封存原始回覆，在推進時驗證輸出；不合法輸出保留原文並消耗重試預算。未收件不算失敗。重試要使用新的隔離上下文。

7. 開場正反各一個獨立上下文，不看對方開場。反駁階段可續接各自開場，但只給已發布的任務包（兩份開場，不含對方反駁）。只有這一輪反駁。
8. 終評優先使用初評的 `resume_context_id` 續接同一角色；本會話對應工具為 `followup_task`。若代理已被回收、續接不可用或槽位不足，重新建立隔離上下文，使用終評任務包中該角色自己的初評與相同辯論。

續接收件必須填入相同的實際 ID：

```bash
python -m agent_council native submit <評估ID> final.software_engineer /tmp/engineer-final.json --context-id <初評實際代理ID> --context-mode resumed
```

重新建立則使用新的 ID 與 `--context-mode fresh`。不允許跨角色共用上下文，也不能把看到過其他陪審員投票的父上下文作為陪審上下文。

9. 重複收件與推進，直到產生 `report.md`，再用 `report <評估ID>` 與 `list` 檢視。成功時共有 28 份任務輸出，代表十二次初評、四次辯論、十二次終評，不能只保存一份綜合回覆。

## 真實失敗

```bash
python -m agent_council native fail <評估ID> initial.scientist --reason '子代理工具啟動失敗'
python -m agent_council native advance <評估ID>
```

預設可重試一次。超過預算便明確標記失敗；不能改填 `ABSTAIN` 或 mock 輸出。其餘角色可以繼續，最終報告會標示不完整並暫緩整體建議。

## 專案自訂代理與版本差異

`.codex/agents/` 提供一份主協調、十二份陪審與兩份辯論的 standalone TOML。每份含官方支持的 `name`、`description`、`developer_instructions`，不固定模型、不改權限。它們是衍生指示檔，不是已經啟動的代理。

可在支援的客戶端要求使用 `council_software_engineer` 等名稱。若目前的 spawn 工具沒有選擇自訂代理的參數，就用一般新上下文代理並傳遞完整任務包；不臆造不存在的 `agent_type`。本工作階段的工具只暴露 `task_name`、`fork_turns` 等參數，尚未驗證 TOML 自動載入。

更新角色後同步：

```bash
python scripts/generate_agents.py --write
python scripts/generate_agents.py --check
```

Python 的收件欄位是操作者聲明，無法加密認證模型確實執行過。請保留 Codex 工具紀錄並誠實描述執行來源。本版為無工具評議：如需新外部證據，先由使用者把資料加入原提案，再以新評估 ID 重跑。
