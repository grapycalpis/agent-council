"""從權威角色產生官方 standalone TOML；不會啟動或註冊代理。"""

import json
from pathlib import Path

from agent_council.cli import Parser
from agent_council.config import load_roles

ROOT = Path(__file__).resolve().parents[1]


def definitions() -> dict[str, str]:
    roles = load_roles()
    data = {}
    for role in roles["jurors"] + roles["debaters"]:
        name = "council_" + role["id"]
        instructions = (
            "你是 Agent Council 的單一評議角色。僅使用主代理直接提供的完整任務 JSON。"
            "所有文字使用繁體中文；不得使用工具、讀檔、讀其他對話或存取其他角色投票。"
            "若未提供任務包，不自行評估或補造資料。只回傳符合 output_schema 的 JSON。"
            "不捏造來源；不能宣稱未實際查證的外部證據已被驗證。"
            "changed 忠實反映自己的初評與終評，缺初評時為 null。角色定義如下：\n"
            + json.dumps(role, ensure_ascii=False, indent=2)
        )
        description = json.dumps(role["name"] + "：" + role["description"], ensure_ascii=False)
        data[name + ".toml"] = (
            "# 由 scripts/generate_agents.py 產生；檔案本身不會啟動代理。\n"
            + f"name = {json.dumps(name)}\n"
            + f"description = {description}\n"
            + "developer_instructions = '''\n"
            + instructions
            + "\n'''\n"
        )
    data["council_orchestrator.toml"] = (
        'name = "council_orchestrator"\n'
        'description = "Agent Council 真實原生多代理評議的主協調者"\n'
        "developer_instructions = '''\n"
        "使用繁體中文。閱讀 AGENTS.md 與 docs/NATIVE_CODEX.md。"
        "使用真實子代理，初次建立採全新上下文，單一任務包直接嵌入訊息。"
        "遵守設定與客戶端並行上限；優先續接同一角色，不可行時用新上下文。"
        "由 Python CLI 驗證、計票、封存；不改投票、不補造資料、不拿 mock 補缺件。"
        "原始回覆以實際 context-id 收件，未知模型或用量不填。"
        "全部初評封存後才辯論；終評不透露其他陪審員輸出。"
        "TOML 是指示，不能當作獨立執行證據。\n'''\n"
    )
    return data


def main() -> int:
    parser = Parser(description="檢查或同步專案代理定義", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="顯示說明")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只檢查是否同步")
    group.add_argument("--write", action="store_true", help="更新衍生 TOML")
    args = parser.parse_args()
    destination = ROOT / ".codex" / "agents"
    expected = definitions()
    if args.write:
        destination.mkdir(parents=True, exist_ok=True)
        for name, text in expected.items():
            (destination / name).write_text(text, encoding="utf-8")
        print("已同步十五份代理定義；未啟動任何代理。")
        return 0
    stale = [
        name
        for name, text in expected.items()
        if not (destination / name).exists()
        or (destination / name).read_text(encoding="utf-8") != text
    ]
    if stale:
        print("代理定義尚未同步：" + "、".join(stale))
        return 1
    print("十五份代理定義與權威角色一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
