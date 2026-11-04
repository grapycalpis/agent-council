"""JSON Schema 與跨輸出約束；拒絕不合法結果，不修改投票。"""

from jsonschema import Draft202012Validator

from .config import schema
from .domain import CouncilError, Json


def validate(data: object, name: str) -> None:
    errors = sorted(Draft202012Validator(schema(name)).iter_errors(data), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        path = ".".join(map(str, error.absolute_path)) or "根節點"
        # jsonschema 的英文內部錯誤不直接當作使用者介面。
        raise CouncilError(f"{name} 資料不符合契約：{path}（規則：{error.validator}）")


def validate_output(task: Json, output: Json) -> None:
    errors = list(Draft202012Validator(task["output_schema"]).iter_errors(output))
    if errors:
        error = errors[0]
        path = ".".join(map(str, error.absolute_path)) or "根節點"
        raise CouncilError(f"代理輸出不符合封存契約：{path}（規則：{error.validator}）")
    evidence = output.get("important_evidence", output.get("evidence", []))
    if any(item["status"] == "verified" for item in evidence):
        raise CouncilError("此版本採無工具隔離執行，不能聲稱已查證外部證據")
    if output["agent_id"] != task["agent_id"]:
        raise CouncilError("代理回覆 ID 與任務不符")
    if task["phase"] == "final":
        visible = {
            "proposal": task["payload"].get("idea"),
            "own_initial": task["payload"]["own_initial"],
            **task["payload"].get("debate", {}),
        }
        cited = [entry["source"] for entry in output.get("disputed_assumptions", [])]
        cited += [
            source for entry in output.get("contradictions", []) for source in entry["sources"]
        ]
        if any(visible.get(source) is None for source in cited):
            raise CouncilError("爭議或矛盾引用了該角色不可見或缺失的來源")
        initial = task["payload"]["own_initial"]
        if initial is not None and output["changed"] != (initial["vote"] != output["vote"]):
            raise CouncilError("立場變動欄位與初評／終評投票不一致")
        if initial is None and output["changed"] is not None:
            raise CouncilError("缺少有效初評時，立場變動必須為 null")
    if task["phase"] in {"opening", "rebuttal"} and output["phase"] != task["phase"]:
        raise CouncilError("辯論回覆階段不符")
