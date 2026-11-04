# 驗證紀錄

日期：2026-11-04（Asia/Taipei）。本地使用 macOS、CPython 3.12.14。下列自動測試全部離線，不呼叫 LLM。

| 檢查 | 結果 |
|---|---|
| `python -m pytest -q` | 64 項通過 |
| `ruff check .` | 通過 |
| `ruff format --check .` | 通過 |
| `python scripts/generate_agents.py --check` | 十五份代理檔與角色同步 |
| 十五份 standalone TOML 解析 | 通過；不等於客戶端載入實測 |
| `python -m agent_council validate` | 設定、角色、七種 schema、28 筆 fixture 有效 |
| `python -m agent_council demo` | 全流程完成，產生十四節中文報告與 JSON |
| `python -m agent_council run ... --backend native` | 正確停在十二份獨立初評待辦，不自動模擬 |
| sdist／wheel 建置 | 通過，執行所需 YAML、提示、schema、fixture 均封裝 |
| wheel 全新環境、儲存庫外執行 | `validate`、`demo`、console script `list` 通過 |
| Python 3.11／3.12 GitHub Actions | 已建立工作流程，遠端結果以 PR 檢查為準 |

## 重要測試範圍

角色完整性與重複 ID、輸入及 YAML 安全載入、空白標題、四種投票、序位分數與布林誤用、缺件、棄權與失敗分離、初終計票、嚴格多數與平手、立場變化一致性、來源可見性、原始無效 JSON 保留、重試預算、並行上限、程序鎖、不可覆寫保存、設定快照、階段屏障、相同終評辯論材料、收尾中斷復原、十四節報告與個別來源、確定性端到端重播、原生收件完整傳輸模擬與 context ID 防混用。

## 真實執行界線

只實際啟動過一個能力探測子代理並續接第二輪。尚未執行完整真實十二位陪審員評估。原生傳輸測試使用合成 ID 與 fixture，不能視為 LLM 執行證據。探測原文與 CLI 版本見 [能力紀錄](CAPABILITIES.md)。
