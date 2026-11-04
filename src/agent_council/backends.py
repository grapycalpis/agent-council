"""後端只執行任務；不參與計票、不改寫回覆。"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from .config import resource_text
from .domain import Capabilities, CouncilError, Json, PendingTask, Response
from .storage import read_json, timestamp, write_once
from .validation import validate


class Backend(Protocol):
    capabilities: Capabilities

    def execute(self, task: Json, attempt: int, directory: Path) -> Response: ...


class MockBackend:
    capabilities = Capabilities("mock", "mock", False, False, False, "deterministic-fixture-v1")

    def __init__(self, fixture: Json | None = None):
        self.fixture = fixture or json.loads(resource_text("fixtures/demo.json"))

    def execute(self, task: Json, attempt: int, directory: Path) -> Response:
        if task["payload"]["idea"] != self.fixture["idea"]:
            raise CouncilError("模擬 fixture 只適用其附帶的示例提案，不能當作新提案評估")
        output = deepcopy(self.fixture["responses"][task["task_id"]])
        if task["phase"] == "final" and task["payload"]["own_initial"] is None:
            output["changed"] = None
        return Response(output, "mock-" + task["task_id"], self.capabilities.model)


class NativeBackend:
    # 能力來自操作者所在的 Codex 客戶端；Python 不會呼叫不存在的 spawn API。
    capabilities = Capabilities("native", "native_attested", True, True, False)

    def execute(self, task: Json, attempt: int, directory: Path) -> Response:
        path = directory / "responses" / f"{task['task_id']}.{attempt}.json"
        if not path.exists():
            raise PendingTask(task["task_id"])
        receipt = read_json(path)
        validate(receipt, "receipt")
        if receipt["task_id"] != task["task_id"] or receipt["attempt"] != attempt:
            raise CouncilError("收件憑據與任務／嘗試次數不符")
        return Response(
            **{
                k: receipt[k]
                for k in (
                    "output",
                    "context_id",
                    "model",
                    "token_usage",
                    "provenance",
                    "context_mode",
                )
            }
        )


def submit_native(
    directory: Path,
    task_id: str,
    output: Json,
    context_id: str,
    *,
    context_mode: str = "fresh",
    model: str | None = None,
    token_usage: int | None = None,
) -> Path:
    """原生執行者提交工具實際產生的回覆；識別資料屬操作者聲明，非加密認證。"""
    snapshot = read_json(directory / "snapshot.json")
    if snapshot["settings"]["backend"] != "native":
        raise CouncilError("模擬評估不接受原生回覆")
    state = read_json(directory / "state.json")
    record = state["records"].get(task_id)
    if not record or record["status"] != "pending":
        raise CouncilError("此任務不存在或目前不接受提交")
    task = read_json(directory / "tasks" / f"{task_id}.json")
    prior = task.get("resume_context_id")
    if context_mode == "resumed" and (prior is None or prior != context_id):
        raise CouncilError("續接模式必須使用該代理先前的上下文 ID")
    if context_mode == "fresh" and prior == context_id:
        raise CouncilError("重用上下文必須明確記錄 resumed")
    # 同一上下文只能屬於同一角色；避免十二位陪審員實為同一對話。
    for existing in (directory / "responses").glob("*.json"):
        receipt = read_json(existing)
        if receipt["context_id"] == context_id:
            other_phase, other_agent = receipt["task_id"].split(".")
            if other_agent != task["agent_id"] or other_phase == task["phase"]:
                raise CouncilError("同一上下文不可跨角色或作為同階段重新執行的代理")
            if context_mode != "resumed":
                raise CouncilError("已有上下文只能使用續接模式")
    receipt = {
        "task_id": task_id,
        "attempt": record["attempt"],
        "output": output,
        "context_id": context_id,
        "context_mode": context_mode,
        "model": model,
        "token_usage": token_usage,
        "provenance": "operator_attested",
        "submitted_at": timestamp(),
    }
    validate(receipt, "receipt")
    path = directory / "responses" / f"{task_id}.{record['attempt']}.json"
    write_once(path, receipt)
    return path


def backend_for(snapshot: Json) -> Backend:
    if snapshot["settings"]["backend"] == "native":
        return NativeBackend()
    return MockBackend(snapshot["fixture"])
