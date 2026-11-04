"""具有階段屏障與可恢復檢查點的主協調流程。"""

import hashlib
import platform
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .aggregation import aggregate
from .backends import Backend, MockBackend, backend_for
from .config import resource_text, schema
from .domain import PHASES, CouncilError, Json, PendingTask
from .reporting import render_report
from .storage import Store, atomic_json, encode, read_json, timestamp, write_once
from .validation import validate, validate_output


class Workflow:
    def __init__(self, store: Store):
        self.store = store

    def create(self, idea: Json, settings: Json, roles: Json, backend: Backend) -> Path:
        validate(idea, "idea")
        validate(settings, "settings")
        if backend.capabilities.name != settings["backend"]:
            raise CouncilError("設定後端與實際執行後端不一致")
        if isinstance(backend, MockBackend) and idea != backend.fixture["idea"]:
            raise CouncilError("此 fixture 不適用輸入提案")
        snapshot: Json = {
            "format_version": 1,
            "software": {
                "agent_council": version("agent-council"),
                "python": platform.python_version(),
                "platform": platform.system(),
                "PyYAML": version("PyYAML"),
                "jsonschema": version("jsonschema"),
            },
            "settings": deepcopy(settings),
            "roles": deepcopy(roles),
            "backend": backend.capabilities.snapshot(),
            "rubric": resource_text("rubric.md"),
            "prompts": {p: resource_text(f"prompts/{p}.md") for p in PHASES},
            "schemas": {p: schema(p) for p in ("initial", "final", "debate")},
            "limitations": [
                "多數票不是成功或正確的機率；共識不構成證明。",
                "專業角色是模型視角，不是合格人類專家的驗證意見。",
                "原生收件的上下文與模型資訊由操作者聲明，本工具無法獨立認證。",
                "上下文獨立不代表模型偏誤獨立；共用檔案系統仍需遵守讀取邊界。",
                "沒有自動外部研究；未查證來源必須明列。",
            ],
        }
        if isinstance(backend, MockBackend):
            snapshot["fixture"] = deepcopy(backend.fixture)
        return self.store.create(idea, snapshot)

    def _tasks(self, directory: Path, state: Json, snapshot: Json, phase: str) -> list[Json]:
        roles = snapshot["roles"]["jurors" if phase in {"initial", "final"} else "debaters"]
        records = state["records"]

        def own_output(key: str) -> Any:
            record = records.get(key, {})
            return record["response"]["output"] if record.get("status") == "ok" else None

        tasks = []
        for role in roles:
            rid = role["id"]
            payload: Json = {
                "idea": read_json(directory / "idea.json"),
                "role": role,
                "rubric": snapshot["rubric"],
            }
            previous = None
            if phase == "rebuttal":
                payload["openings"] = {a: own_output(f"opening.{a}") for a in ("pro", "con")}
                previous = records.get(f"opening.{rid}", {}).get("response", {}).get("context_id")
            if phase == "final":
                payload["own_initial"] = own_output(f"initial.{rid}")
                payload["debate"] = {
                    f"{p}.{a}": own_output(f"{p}.{a}")
                    for p in ("opening", "rebuttal")
                    for a in ("pro", "con")
                }
                previous = records.get(f"initial.{rid}", {}).get("response", {}).get("context_id")
            schema_name = phase if phase in {"initial", "final"} else "debate"
            task = {
                "task_id": f"{phase}.{rid}",
                "phase": phase,
                "agent_id": rid,
                "instruction": snapshot["prompts"][phase],
                "payload": payload,
                "schema_name": schema_name,
                "output_schema": snapshot["schemas"][schema_name],
                "resume_context_id": previous,
                "isolation": "僅使用本任務包；不要呼叫工具、讀檔或讀取其他對話。",
            }
            task["sha256"] = hashlib.sha256(encode(task).encode()).hexdigest()
            tasks.append(task)
        return tasks

    def _execute(
        self, task: Json, record: Json, backend: Backend, directory: Path, max_retries: int
    ) -> Json:
        record = deepcopy(record)
        while record["attempt"] <= max_retries + 1:
            attempt = record["attempt"]
            artifact = directory / "attempts" / f"{task['task_id']}.{attempt}.json"
            if artifact.exists():
                # 崩潰復原時不重新呼叫模型或覆寫既有原始回覆。
                saved = read_json(artifact)
                if saved["status"] == "ok":
                    record.update(status="ok", response=saved["response"])
                    return record
                error = saved["error"]
            else:
                try:
                    response = backend.execute(deepcopy(task), attempt, directory)
                except PendingTask:
                    record["status"] = "pending"
                    return record
                except Exception as exc:
                    error = f"後端執行失敗：{type(exc).__name__}：{exc}"
                    write_once(
                        artifact, {"status": "error", "error": error, "recorded_at": timestamp()}
                    )
                else:
                    try:
                        validate_output(task, response.output)
                    except CouncilError as exc:
                        error = str(exc)
                        write_once(
                            artifact,
                            {
                                "status": "error",
                                "error": error,
                                "response": response.snapshot(),
                                "recorded_at": timestamp(),
                            },
                        )
                    else:
                        write_once(
                            artifact,
                            {
                                "status": "ok",
                                "response": response.snapshot(),
                                "recorded_at": timestamp(),
                            },
                        )
                        record.update(status="ok", response=response.snapshot())
                        return record
            record["errors"].append({"attempt": attempt, "error": error})
            record["attempt"] += 1
        record["status"] = "failed"
        return record

    def advance(self, directory: Path, backend: Backend | None = None) -> Json:
        with self.store.lock(directory):
            state = read_json(directory / "state.json")
            if state["status"] in {"complete", "incomplete"}:
                return state
            snapshot = read_json(directory / "snapshot.json")
            backend = backend or backend_for(snapshot)
            if backend.capabilities.snapshot() != snapshot["backend"]:
                raise CouncilError("續跑後端能力與封存設定不同")
            settings = snapshot["settings"]
            while state["phase_index"] < len(PHASES):
                phase = PHASES[state["phase_index"]]
                tasks = self._tasks(directory, state, snapshot, phase)
                for task in tasks:
                    path = directory / "tasks" / f"{task['task_id']}.json"
                    if not path.exists():
                        write_once(path, task)
                    elif read_json(path) != task:
                        raise CouncilError("封存任務與重建任務不一致，請檢查檔案完整性")
                    state["records"].setdefault(
                        task["task_id"],
                        {
                            "status": "pending",
                            "attempt": 1,
                            "errors": [],
                        },
                    )
                # 先保存待辦，讓原生收件在 Python 結束後也能運作。
                atomic_json(directory / "state.json", state)
                active = [t for t in tasks if state["records"][t["task_id"]]["status"] == "pending"]
                with ThreadPoolExecutor(max_workers=settings["max_concurrency"]) as executor:
                    futures = [
                        (
                            t,
                            executor.submit(
                                self._execute,
                                t,
                                state["records"][t["task_id"]],
                                backend,
                                directory,
                                settings["max_retries"],
                            ),
                        )
                        for t in active
                    ]
                    for task, future in futures:
                        state["records"][task["task_id"]] = future.result()
                        atomic_json(directory / "state.json", state)
                if any(state["records"][t["task_id"]]["status"] == "pending" for t in tasks):
                    state["status"] = "awaiting_native"
                    atomic_json(directory / "state.json", state)
                    return state
                # 含失敗的階段也封存；後續任務只接收明確的 null 缺件，不補造資料。
                checkpoint = {
                    "phase": phase,
                    "completed_at": timestamp(),
                    "records": {t["task_id"]: state["records"][t["task_id"]] for t in tasks},
                }
                checkpoint_path = directory / "phases" / f"{phase}.json"
                if not checkpoint_path.exists():
                    write_once(checkpoint_path, checkpoint)
                state["phase_log"].append(phase)
                state["phase_index"] += 1
                state["status"] = "running"
                atomic_json(directory / "state.json", state)
            summary = aggregate(state, snapshot["roles"])
            state["finished_at"] = state.get("finished_at", timestamp())
            state["status"] = "finalizing"
            atomic_json(directory / "state.json", state)
            state["status"] = "complete" if summary["complete"] else "incomplete"
            # 最終封存是不可覆寫的；可安全重進崩潰後尚未更新 state 的收尾。
            for name, data, is_text in (
                ("aggregate.json", summary, False),
                ("result.json", {"state": state, "summary": summary}, False),
                (
                    "report.md",
                    render_report(read_json(directory / "idea.json"), state, snapshot, summary),
                    True,
                ),
            ):
                path = directory / name
                if not path.exists():
                    write_once(path, data, text=is_text)
            atomic_json(directory / "state.json", state)
            return state

    def fail_native(self, directory: Path, task_id: str, reason: str) -> None:
        with self.store.lock(directory):
            state = read_json(directory / "state.json")
            record = state["records"].get(task_id)
            if not record or record["status"] != "pending":
                raise CouncilError("只能標記目前待辦任務失敗")
            receipt = directory / "responses" / f"{task_id}.{record['attempt']}.json"
            if receipt.exists():
                raise CouncilError("此任務已有收件，請先繼續流程")
            artifact = directory / "attempts" / f"{task_id}.{record['attempt']}.json"
            write_once(
                artifact,
                {"status": "error", "error": "原生代理失敗：" + reason, "recorded_at": timestamp()},
            )
            # advance 會套用同樣的重試預算；操作者不需也不能補成棄權票。
