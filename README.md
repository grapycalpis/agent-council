# Agent Council V1.0

一個可重複使用、保留歷史與少數意見的提案評議工具。主協調器安排十二個專業角色獨立初評，再由正反代理開場與單輪反駁，最後收集十二位陪審員的終評，產生可追溯的繁體中文報告。

這是決策支援工具。角色是模型視角，共識不是事實，多數票不代表成功機率。

## 已實作範圍

| 後端／功能 | 狀態 | 實際行為 |
|---|---|---|
| `mock` | 已實作、已測試 | 固定 fixture 重播 28 筆輸出，完全離線、零 LLM 呼叫 |
| `native` | 已實作、協定已測試 | 發布隔離任務包，由互動 Codex 啟動真實子代理並收件 |
| 原生建立與續接能力 | 已實測一個探測代理、兩輪 | 驗證新上下文與原代理續接；不是十二人評估 |
| 完整真實十二人評估 | 尚未執行 | 不把傳輸協定測試或 mock 報告當作真實評估 |
| `.codex/agents/*.toml` | 已提供、語法與同步檢查通過 | 官方文件支持的專案代理定義；此工作階段未驗證自動載入 |
| Python 自動呼叫聊天內 `spawn_agent` | 不支援 | 聊天工具不是 Python 可匯入的函式 |
| 自動外部研究／可選付費 API | V1 未實作 | 不要求 API 金鑰，不隱性呼叫付費 API |

原生協調須在提供獨立子代理工具的 Codex 互動工作階段完成；CLI 的 `run` 會先停在待辦，不會用單一上下文扮演十二人。詳細實測與來源見 [執行能力紀錄](docs/CAPABILITIES.md)。

## 安裝

需要 Python 3.11+。目前驗證環境為 macOS／Python 3.12；檔案鎖使用 POSIX `flock`，支援 macOS 與 Linux，Windows 原生環境尚不支援。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m agent_council inspect
python -m agent_council validate
```

若使用 `uv`，可改用：

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e '.[dev]'
```

執行期間只需要 PyYAML 與 jsonschema；pytest、Ruff、build 是開發套件。所有範例均先從儲存庫根目錄執行並啟用虛擬環境。

## 先跑離線示例

```bash
python -m agent_council demo
python -m agent_council list
python -m agent_council report <評估ID>
```

`demo` 每次建立新的 `results/<評估ID>/`，包含輸入、設定快照、28 個隔離任務、原始回覆、階段封存、計票 JSON 與十四節中文報告。示例提案是「小型團隊試行每週一天遠端工作」。模擬標記會出現在 CLI、報告及後端紀錄；fixture 僅可用於其附帶提案。

`<評估ID>` 等角括號表示請替換為實際輸出，不是可直接貼上的字面參數。

## 第一次真實十二人評估

```bash
python -m agent_council run ideas/examples/example.yaml --backend native
python -m agent_council native prompt <評估ID>
```

把第二個命令產生的繁體中文協調指令貼入同一專案的 Codex 聊天，明確要求使用真實子代理。Codex 主代理依 [原生執行手冊](docs/NATIVE_CODEX.md)，以新上下文分批啟動十二位陪審員，再完成正反辯論與終評，透過 `native submit` 收件、`native advance` 推進流程。

本次會話已確認的上限為包含主代理在內四個活躍代理，因此預設並行三個子代理。實際啟動數還要遵守客戶端可用空位。每位角色有自己的上下文，十二人不必同時存在；不能續接時用全新上下文及該角色自己的初評包。重試需用新的上下文。

查看待辦及隔離任務：

```bash
python -m agent_council native tasks <評估ID>
python -m agent_council native task <評估ID> initial.software_engineer
```

自行建立提案時，複製 [範例 YAML](ideas/examples/example.yaml)，填入 `title`、`description`、`context`、`goals`、`constraints`，可選填 `evidence`。背景不明可留空，不能補造事實。每筆證據是 `claim` 與可為 `null` 的 `source`。提案及輸出結構見 [JSON Schema](src/agent_council/data/schemas/)。

## 設定與歷史

```bash
python -m agent_council --config config/default.yaml validate
python -m agent_council --results /tmp/council-results demo
python -m agent_council --roles /tmp/my-roles.yaml validate
```

全域選項放在子命令前。`--roles` 可以調整專業問題與指示，須保留十二個指定角色 ID 與正反角色。權威角色定義為 [roles.yaml](src/agent_council/data/roles.yaml)，共用評分規則為 [rubric.md](src/agent_council/data/rubric.md)。

既有評估一律使用封存的角色、提示、schema 與設定，不受後續設定檔變更影響。最終結果不覆寫；進行中狀態才原子更新。`results/` 預設忽略 Git，以免提交私密提案。若要保存已審查紀錄到 GitHub：

```bash
git add -f results/<評估ID>
git commit -m '保存已審查的提案評估紀錄'
```

提交前請自行確認提案、證據與回覆的公開範圍。庫內提供可公開的 [模擬報告](docs/examples/mock-report.md) 與 [計票示例](docs/examples/mock-aggregate.json)。

## 架構與品質

`domain` 定義領域型別；`config`／`validation` 處理契約；`backends` 隔離執行來源；`workflow` 控制階段與並行；`aggregation` 純函式計票；`reporting` 只根據個別輸出產生報告；`storage` 保存不可覆寫的歷史；`cli` 提供操作介面。不需要資料庫、網頁、Docker 或訊息佇列。

```bash
python -m pytest -q
ruff check .
ruff format --check .
python scripts/generate_agents.py --check
```

本地驗證結果：64 項測試通過；詳細結果見 [驗證紀錄](docs/VALIDATION.md)。GitHub Actions 會在 Python 3.11 與 3.12 執行相同核心檢查。

更多說明：[架構](docs/ARCHITECTURE.md)、[流程](docs/WORKFLOW.md)、[限制](docs/LIMITATIONS.md)、[原生手冊](docs/NATIVE_CODEX.md)。
