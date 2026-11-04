from copy import deepcopy

import pytest

from agent_council.backends import NativeBackend, submit_native
from agent_council.domain import CouncilError
from agent_council.storage import Store, read_json
from agent_council.workflow import Workflow


@pytest.fixture
def native(tmp_path, fixture, roles, settings):
    settings["backend"] = "native"
    workflow = Workflow(Store(tmp_path / "native"))
    directory = workflow.create(fixture["idea"], settings, roles, NativeBackend())
    workflow.advance(directory)
    return workflow, directory


def test_native_publishes_only_initial_phase(native):
    _, directory = native
    state = read_json(directory / "state.json")
    assert state["status"] == "awaiting_native"
    assert len(state["records"]) == 12
    assert not (directory / "report.md").exists()
    assert not list((directory / "tasks").glob("opening.*"))


def test_native_file_bridge_end_to_end_is_only_transport_simulation(native, fixture):
    # 測試檔案傳輸協定，不代表實際啟動過任何 LLM。
    workflow, directory = native
    for _phase in ("initial", "opening", "rebuttal", "final"):
        state = read_json(directory / "state.json")
        for key, record in state["records"].items():
            if record["status"] == "pending":
                task = read_json(directory / "tasks" / f"{key}.json")
                previous = task["resume_context_id"]
                context_id = previous or f"transport-test-{task['agent_id']}"
                submit_native(
                    directory,
                    key,
                    deepcopy(fixture["responses"][key]),
                    context_id,
                    context_mode="resumed" if previous else "fresh",
                )
        state = workflow.advance(directory)
    assert state["status"] == "complete"
    assert all(
        r["response"]["provenance"] == "operator_attested" for r in state["records"].values()
    )
    assert "由操作者聲明" in (directory / "report.md").read_text()
    assert "無法取得" in (directory / "report.md").read_text()


def test_native_duplicate_context_rejected(native, fixture):
    _, directory = native
    submit_native(
        directory,
        "initial.scientist",
        fixture["responses"]["initial.scientist"],
        "actual-context-a",
    )
    with pytest.raises(CouncilError, match="上下文"):
        submit_native(
            directory,
            "initial.skeptic",
            fixture["responses"]["initial.skeptic"],
            "actual-context-a",
        )


def test_native_duplicate_submission_not_overwritten(native, fixture):
    _, directory = native
    submit_native(directory, "initial.scientist", fixture["responses"]["initial.scientist"], "a")
    with pytest.raises(FileExistsError):
        submit_native(
            directory, "initial.scientist", fixture["responses"]["initial.scientist"], "b"
        )


def test_native_cannot_claim_resume_without_original(native, fixture):
    _, directory = native
    with pytest.raises(CouncilError, match="續接"):
        submit_native(
            directory,
            "initial.scientist",
            fixture["responses"]["initial.scientist"],
            "a",
            context_mode="resumed",
        )


def test_native_failed_task_uses_retry_budget(native):
    workflow, directory = native
    workflow.fail_native(directory, "initial.scientist", "工具未能啟動")
    state = workflow.advance(directory)
    assert state["records"]["initial.scientist"]["attempt"] == 2
    workflow.fail_native(directory, "initial.scientist", "第二次仍失敗")
    state = workflow.advance(directory)
    assert state["records"]["initial.scientist"]["status"] == "failed"
    assert "response" not in state["records"]["initial.scientist"]
    assert state["phase_index"] == 0  # 其他十一人仍待回覆。


def test_native_out_of_phase_submission_rejected(native, fixture):
    _, directory = native
    with pytest.raises(CouncilError, match="不存在"):
        submit_native(directory, "final.scientist", fixture["responses"]["final.scientist"], "a")


def test_native_unverified_source_cannot_be_promoted(native, fixture):
    _, directory = native
    # 直接驗證辯論契約：無工具執行時不能聲稱已查證研究。
    from agent_council.config import schema
    from agent_council.validation import validate_output

    output = fixture["responses"]["opening.pro"]
    output["evidence"][0].update(status="verified", source="https://example.com/source")
    task = {
        "agent_id": "pro",
        "phase": "opening",
        "schema_name": "debate",
        "output_schema": schema("debate"),
        "payload": {},
    }
    with pytest.raises(CouncilError, match="查證"):
        validate_output(task, output)


def test_invalid_native_output_is_archived_then_retried(native, fixture):
    workflow, directory = native
    invalid = deepcopy(fixture["responses"]["initial.scientist"])
    invalid["vote"] = "YES"
    receipt = submit_native(directory, "initial.scientist", invalid, "raw-invalid-context")
    assert read_json(receipt)["output"]["vote"] == "YES"
    state = workflow.advance(directory)
    assert state["records"]["initial.scientist"]["attempt"] == 2
    raw = read_json(directory / "attempts" / "initial.scientist.1.json")
    assert raw["response"]["output"]["vote"] == "YES"
    assert raw["status"] == "error"


def test_non_object_native_json_preserved_for_failure_audit(native):
    workflow, directory = native
    path = submit_native(directory, "initial.scientist", ["錯誤陣列"], "array-context")
    assert read_json(path)["output"] == ["錯誤陣列"]
    state = workflow.advance(directory)
    assert state["records"]["initial.scientist"]["attempt"] == 2
