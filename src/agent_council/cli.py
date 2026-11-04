"""繁體中文命令列：模擬與原生互動流程明確分流。"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from .backends import MockBackend, NativeBackend, submit_native
from .config import load_document, load_roles, load_settings, resource_text, schema
from .domain import PHASES, CouncilError, Json
from .storage import Store, encode, read_json
from .validation import validate
from .workflow import Workflow


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "參數錯誤，請使用 --help 檢查命令與必要參數。\n")

    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "用法：")
            .replace("positional arguments:", "命令或位置參數：")
            .replace("options:", "選項：")
        )

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法：")


def make_parser() -> Parser:
    parser = Parser(description="Agent Council：可追溯的十二角色提案評議", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="顯示說明")
    parser.add_argument("--results", type=Path, default=Path("results"), help="結果根目錄")
    parser.add_argument("--config", type=Path, help="設定 YAML 路徑")
    parser.add_argument("--roles", type=Path, help="自訂角色 YAML 路徑")
    commands = parser.add_subparsers(dest="command", required=True, title="命令")

    def command(name: str, help_text: str, parent=commands) -> argparse.ArgumentParser:
        child = parent.add_parser(name, help=help_text, description=help_text, add_help=False)
        child.add_argument("-h", "--help", action="help", help="顯示說明")
        return child

    command("inspect", "檢視本機工具與後端能力；不呼叫模型")
    command("validate", "驗證設定、十二角色、schema 與示例 fixture")
    command("demo", "完整執行確定性模擬；不啟動真實代理")
    run = command("run", "建立評估；預設輸出原生待辦，不會自動角色扮演")
    run.add_argument("idea", type=Path, help="提案 YAML 或 JSON")
    run.add_argument("--backend", choices=("native", "mock"), help="明確指定後端")
    command("list", "列出歷史評估")
    report = command("report", "讀取既有報告")
    report.add_argument("evaluation_id", help="評估 ID")
    native = command("native", "操作 Codex 原生互動收件流程")
    sub = native.add_subparsers(dest="native_command", required=True, title="原生操作")
    for name, text in (
        ("tasks", "列出目前待辦"),
        ("advance", "套用回覆並推進至下一階段"),
        ("prompt", "顯示可貼入 Codex 的協調指令"),
    ):
        child = command(name, text, sub)
        child.add_argument("evaluation_id", help="評估 ID")
    task = command("task", "讀取單一隔離任務包", sub)
    task.add_argument("evaluation_id", help="評估 ID")
    task.add_argument("task_id", help="任務 ID")
    submit = command("submit", "提交實際子代理原始 JSON；識別資訊為操作者聲明", sub)
    submit.add_argument("evaluation_id", help="評估 ID")
    submit.add_argument("task_id", help="任務 ID")
    submit.add_argument("output", type=Path, help="原始 JSON 回覆檔案")
    submit.add_argument("--context-id", required=True, help="實際工具回傳的上下文／代理 ID")
    submit.add_argument(
        "--context-mode", choices=("fresh", "resumed"), default="fresh", help="新建或續接"
    )
    submit.add_argument("--model", help="工具有提供時填入模型 ID；不可猜測")
    submit.add_argument("--token-usage", type=int, help="工具有提供時填入用量；否則省略")
    fail = command("fail", "記錄代理失敗；使用相同重試預算", sub)
    fail.add_argument("evaluation_id", help="評估 ID")
    fail.add_argument("task_id", help="任務 ID")
    fail.add_argument("--reason", required=True, help="失敗原因")
    return parser


def display_state(state: Json, directory: Path) -> None:
    print(f"評估 ID：{state['evaluation_id']}")
    if state["status"] == "awaiting_native":
        print("等待真實原生子代理：Python 不會自行啟動代理，請執行 native prompt／tasks。")
    else:
        print("流程完成。" if state["status"] == "complete" else "流程結束，但評估不完整。")
        print(f"報告：{directory / 'report.md'}")


def native_command(args: argparse.Namespace, store: Store, workflow: Workflow) -> int:
    directory = store.locate(args.evaluation_id)
    if read_json(directory / "snapshot.json")["settings"]["backend"] != "native":
        raise CouncilError("此評估使用模擬後端，不能進行原生收件")
    state = read_json(directory / "state.json")
    action = args.native_command
    if action == "advance":
        display_state(workflow.advance(directory), directory)
    elif action == "submit":
        with store.lock(directory):
            path = submit_native(
                directory,
                args.task_id,
                read_json(args.output),
                args.context_id,
                context_mode=args.context_mode,
                model=args.model,
                token_usage=args.token_usage,
            )
        print(f"已封存原始回覆（推進流程時驗證）：{path}")
    elif action == "fail":
        workflow.fail_native(directory, args.task_id, args.reason)
        print("失敗已記錄；請執行 native advance 套用重試預算。")
    elif action == "task":
        if args.task_id not in state["records"]:
            raise CouncilError("找不到已發布任務")
        print(encode(read_json(directory / "tasks" / f"{args.task_id}.json")), end="")
    elif action == "tasks":
        for task_id, record in state["records"].items():
            if record["status"] == "pending":
                print(
                    f"{task_id}（第 {record['attempt']} 次）→ "
                    f"{directory / 'tasks' / (task_id + '.json')}"
                )
    elif action == "prompt":
        print(f"""請依 docs/NATIVE_CODEX.md，使用真實 Codex 子代理完成評估 {args.evaluation_id}。
結果根目錄：{store.root.resolve()}
請先讀取該評估 snapshot.json 的並行設定與目前 native tasks。
每位陪審員與正反代理初次啟動時均使用全新上下文（fork_turns=none 或等效機制）。
把完整的單一任務 JSON 直接放進子代理訊息；不要把其他任務、對話、票數或目錄傳給它。
禁止陪審／辯論代理使用工具或讀檔，僅回傳符合 output_schema 的 JSON。
有 resume_context_id 時優先續接同一角色；不能續接就新建獨立上下文，填 fresh。
由主代理將原始 JSON 存到暫存檔，使用 native submit 與實際 context-id 收件。
每一批全部收件或記錄失敗後，執行 native advance，重複到產生 report.md。
同時最多啟動設定允許且客戶端有空位的代理數；不能把十二人合成一次角色扮演。
不要使用 MockBackend 補缺件，也不能修改投票以通過驗證。""")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        store = Store(args.results)
        workflow = Workflow(store)
        if args.command == "inspect":
            codex = shutil.which("codex")
            version = "未安裝"
            if codex:
                try:
                    version = subprocess.run(
                        [codex, "--version"], capture_output=True, text=True, check=True, timeout=10
                    ).stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    version = "已找到但無法取得版本"
            print(f"Python：{sys.version.split()[0]}\nCodex CLI：{version}")
            print("模擬後端：已實作，不呼叫 LLM。")
            print("原生後端：已實作互動任務與收件，需由 Codex 客戶端啟動獨立代理。")
            print("此 Python 程序無法自動確認目前聊天是否提供 spawn／續接工具。")
        elif args.command == "validate":
            load_settings(args.config)
            roles = load_roles(args.roles)
            for name in ("idea", "initial", "final", "debate", "receipt", "roles", "settings"):
                Draft202012Validator.check_schema(schema(name))
            fixture = json.loads(resource_text("fixtures/demo.json"))
            validate(fixture["idea"], "idea")
            expected = {
                f"{p}.{r['id']}"
                for p in PHASES
                for r in roles["jurors" if p in {"initial", "final"} else "debaters"]
            }
            if set(fixture["responses"]) != expected:
                raise CouncilError("fixture 任務集合不完整")
            for task_id, output in fixture["responses"].items():
                phase = task_id.split(".")[0]
                validate(output, phase if phase in {"initial", "final"} else "debate")
            print("設定、十二個陪審角色、正反角色、JSON Schema 與 28 筆 fixture 均有效。")
        elif args.command in {"demo", "run"}:
            roles, settings = load_roles(args.roles), load_settings(args.config)
            if args.command == "demo":
                backend = MockBackend()
                idea = backend.fixture["idea"]
                settings["backend"] = "mock"
                print("確定性模擬：沒有啟動真實代理；不能當作實際提案建議。")
            else:
                idea = load_document(args.idea)
                if args.backend:
                    settings["backend"] = args.backend
                backend = MockBackend() if settings["backend"] == "mock" else NativeBackend()
                if settings["backend"] == "mock":
                    print("確定性模擬：沒有啟動真實代理。")
            directory = workflow.create(idea, settings, roles, backend)
            display_state(workflow.advance(directory, backend), directory)
        elif args.command == "list":
            for record in store.summaries():
                mode = "模擬" if record["execution_kind"] == "mock" else "原生互動收件"
                print(f"{record['evaluation_id']}\t{mode}\t{record['status']}\t{record['title']}")
        elif args.command == "report":
            path = store.locate(args.evaluation_id) / "report.md"
            if not path.exists():
                raise CouncilError("報告尚未產生，請先完成原生任務並推進流程")
            print(path.read_text(encoding="utf-8"), end="")
        elif args.command == "native":
            return native_command(args, store, workflow)
        return 0
    except (CouncilError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, CouncilError):
            print(f"錯誤：{exc}", file=sys.stderr)
        elif isinstance(exc, FileExistsError):
            print("錯誤：此封存檔已存在，為保護歷史不會覆寫。", file=sys.stderr)
        else:
            print(
                f"錯誤：無法讀取或處理資料（{type(exc).__name__}），請檢查路徑與格式。",
                file=sys.stderr,
            )
        return 2
