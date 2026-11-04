from copy import deepcopy
from dataclasses import replace
from threading import Lock

import pytest

from agent_council.backends import MockBackend
from agent_council.domain import CouncilError
from agent_council.storage import read_json, write_once


def test_end_to_end_and_deterministic_replay(council, fixture, roles, settings):
    workflow, directory, backend = council
    state = workflow.advance(directory, backend)
    assert state["status"] == "complete"
    assert state["phase_log"] == ["initial", "opening", "rebuttal", "final"]
    assert len(state["records"]) == 28
    summary = read_json(directory / "aggregate.json")
    assert summary["initial"]["counts"] == {
        "SUPPORT": 5,
        "OPPOSE": 2,
        "CONDITIONAL": 3,
        "ABSTAIN": 2,
    }
    assert summary["final"]["counts"] == {"SUPPORT": 4, "OPPOSE": 1, "CONDITIONAL": 6, "ABSTAIN": 1}
    assert summary["final"]["majority"] is None
    assert sum(c["changed"] for c in summary["changes"]) == 3
    for task_id, record in state["records"].items():
        assert record["response"]["output"] == fixture["responses"][task_id]
        assert record["response"]["provenance"] == "mock"
    assert len(list((directory / "attempts").glob("*.json"))) == 28
    assert (directory / "phases" / "initial.json").exists()
    before = (directory / "report.md").read_bytes()
    assert workflow.advance(directory)["status"] == "complete"
    assert (directory / "report.md").read_bytes() == before
    second = workflow.create(fixture["idea"], settings, roles, MockBackend(fixture))
    workflow.advance(second)
    assert second != directory
    assert read_json(second / "aggregate.json") == summary
    assert read_json(second / "snapshot.json") == read_json(directory / "snapshot.json")


def test_phase_barriers_and_isolation(council):
    workflow, directory, backend = council

    class Inspector(MockBackend):
        def execute(self, task, attempt, path):
            payload, phase = task["payload"], task["phase"]
            assert "other_jurors" not in payload and "votes" not in payload
            if phase == "initial":
                assert set(payload) == {"idea", "role", "rubric"}
                assert not (path / "phases" / "initial.json").exists()
            else:
                assert (path / "phases" / "initial.json").exists()
            if phase == "opening":
                assert "openings" not in payload
            if phase == "rebuttal":
                assert set(payload["openings"]) == {"pro", "con"}
                assert all(v["phase"] == "opening" for v in payload["openings"].values())
            if phase == "final":
                assert payload["own_initial"]["agent_id"] == task["agent_id"]
                assert len(payload["debate"]) == 4
            return super().execute(task, attempt, path)

    workflow.advance(directory, Inspector(backend.fixture))
    final_tasks = [read_json(p) for p in (directory / "tasks").glob("final.*.json")]
    assert len(final_tasks) == 12
    assert all(t["payload"]["debate"] == final_tasks[0]["payload"]["debate"] for t in final_tasks)


def test_failed_juror_not_abstention_and_retries_preserved(council):
    workflow, directory, backend = council

    class Broken(MockBackend):
        def execute(self, task, attempt, path):
            if task["task_id"] in {"initial.scientist", "final.scientist"}:
                raise RuntimeError("測試代理失敗")
            return super().execute(task, attempt, path)

    state = workflow.advance(directory, Broken(backend.fixture))
    assert state["status"] == "incomplete"
    result = read_json(directory / "aggregate.json")
    assert result["initial"]["valid_count"] == 11
    assert result["initial"]["counts"]["ABSTAIN"] == 1
    assert result["final"]["counts"]["ABSTAIN"] == 1
    assert result["final"]["missing"] == ["scientist"]
    assert len(state["records"]["final.scientist"]["errors"]) == 2
    assert "暫緩" in (directory / "report.md").read_text()


def test_initial_failure_does_not_invent_position_change(council):
    workflow, directory, backend = council

    class BrokenInitial(MockBackend):
        def execute(self, task, attempt, path):
            if task["task_id"] == "initial.scientist":
                raise RuntimeError("無初評")
            return super().execute(task, attempt, path)

    state = workflow.advance(directory, BrokenInitial(backend.fixture))
    assert state["status"] == "incomplete"
    final = state["records"]["final.scientist"]["response"]["output"]
    assert final["changed"] is None
    summary = read_json(directory / "aggregate.json")
    assert next(c for c in summary["changes"] if c["agent_id"] == "scientist")["changed"] is None


def test_invalid_response_saved_and_not_corrected(council):
    workflow, directory, backend = council

    class Invalid(MockBackend):
        def execute(self, task, attempt, path):
            response = super().execute(task, attempt, path)
            if task["task_id"] == "final.scientist":
                response.output["vote"] = "YES"
            return response

    state = workflow.advance(directory, Invalid(backend.fixture))
    assert state["records"]["final.scientist"]["status"] == "failed"
    raw = read_json(directory / "attempts" / "final.scientist.1.json")
    assert raw["response"]["output"]["vote"] == "YES"
    assert read_json(directory / "aggregate.json")["final"]["valid_count"] == 11


def test_transient_failure_retries(council):
    workflow, directory, backend = council

    class Transient(MockBackend):
        def execute(self, task, attempt, path):
            if task["task_id"] == "initial.scientist" and attempt == 1:
                raise RuntimeError("短暫失敗")
            return super().execute(task, attempt, path)

    state = workflow.advance(directory, Transient(backend.fixture))
    record = state["records"]["initial.scientist"]
    assert state["status"] == "complete"
    assert record["attempt"] == 2
    assert len(record["errors"]) == 1
    assert "短暫失敗" in (directory / "report.md").read_text()


def test_missing_debater_marks_incomplete(council):
    workflow, directory, backend = council

    class BrokenDebate(MockBackend):
        def execute(self, task, attempt, path):
            if task["task_id"] == "opening.con":
                raise RuntimeError("反方失敗")
            return super().execute(task, attempt, path)

    workflow.advance(directory, BrokenDebate(backend.fixture))
    summary = read_json(directory / "aggregate.json")
    assert summary["debate_missing"] == ["opening.con"]
    assert not summary["complete"]
    assert (
        read_json(directory / "tasks" / "final.scientist.json")["payload"]["debate"]["opening.con"]
        is None
    )


def test_bounded_concurrency(council):
    workflow, directory, backend = council
    lock, active, peak = Lock(), 0, 0

    class Measured(MockBackend):
        def execute(self, task, attempt, path):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                return super().execute(task, attempt, path)
            finally:
                with lock:
                    active -= 1

    workflow.advance(directory, Measured(backend.fixture))
    assert peak <= 3


def test_persistence_never_overwrites(council):
    workflow, directory, backend = council
    workflow.advance(directory, backend)
    with pytest.raises(FileExistsError):
        write_once(directory / "idea.json", {"title": "覆寫"})
    assert len(workflow.store.summaries()) == 1
    with pytest.raises(CouncilError):
        workflow.store.locate("../../outside")


def test_configuration_and_inputs_are_snapshotted(council, roles, settings):
    _, directory, backend = council
    snapshot = read_json(directory / "snapshot.json")
    assert snapshot["roles"] == roles
    assert snapshot["settings"] == settings
    assert snapshot["fixture"] == backend.fixture
    assert "schemas" in snapshot and "prompts" in snapshot


def test_reject_backend_change_on_resume(council):
    workflow, directory, backend = council
    backend.capabilities = replace(backend.capabilities, name="something_else")
    with pytest.raises(CouncilError, match="能力"):
        workflow.advance(directory, backend)


def test_fixture_cannot_evaluate_unrelated_idea(council, roles, settings, fixture):
    workflow, _, backend = council
    idea = deepcopy(fixture["idea"])
    idea["title"] = "完全不同的提案"
    with pytest.raises(CouncilError, match="fixture"):
        workflow.create(idea, settings, roles, backend)


def test_report_covers_fourteen_sections_and_traceability(council):
    workflow, directory, backend = council
    workflow.advance(directory, backend)
    report = (directory / "report.md").read_text()
    for number in range(1, 15):
        assert f"## {number}. " in report
    assert "確定性模擬" in report
    assert "不是成功或正確機率" in report
    assert "unknown" in report
    assert "無法取得" in report
    for task_id in backend.fixture["responses"]:
        assert task_id in report


def test_finalization_can_resume_after_interrupted_artifact_write(council, monkeypatch):
    workflow, directory, backend = council
    import agent_council.workflow as module

    original = module.write_once
    interrupted = False

    def crash_once(path, data, **kwargs):
        nonlocal interrupted
        if path.name == "report.md" and not interrupted:
            interrupted = True
            raise OSError("模擬程序中斷")
        return original(path, data, **kwargs)

    monkeypatch.setattr(module, "write_once", crash_once)
    with pytest.raises(OSError):
        workflow.advance(directory, backend)
    assert read_json(directory / "state.json")["status"] == "finalizing"
    state = workflow.advance(directory, backend)
    assert state["status"] == "complete"
    assert (directory / "report.md").exists()
    assert read_json(directory / "result.json")["state"] == state


def test_parallel_writer_lock_is_rejected(council):
    workflow, directory, backend = council
    with workflow.store.lock(directory):
        with pytest.raises(CouncilError, match="另一個程序"):
            workflow.advance(directory, backend)


def test_missing_phase_checkpoint_prevents_complete_quality_status(council, roles):
    from agent_council.aggregation import aggregate

    workflow, directory, backend = council
    state = workflow.advance(directory, backend)
    state["phase_log"].remove("rebuttal")
    summary = aggregate(state, roles)
    assert not summary["complete"]
    assert summary["phase_missing"] == ["rebuttal"]


def test_disputed_assumptions_and_reported_contradictions_remain_attributed(council):
    workflow, directory, backend = council
    # 只測試帶來源的整理機制；這段合成描述不宣稱示例真的矛盾。
    backend.fixture["responses"]["final.skeptic"]["contradictions"] = [
        {"sources": ["opening.pro", "opening.con"], "description": "【測試資料】待查證的矛盾描述"}
    ]
    state = workflow.advance(directory, backend)
    assert state["status"] == "complete"
    summary = read_json(directory / "aggregate.json")
    assert summary["disputed_assumptions"][0]["agent_id"] == "risk_analyst"
    assert summary["contradictions"][0]["agent_id"] == "skeptic"
    report = (directory / "report.md").read_text()
    assert "尚未獨立查證" in report
    assert "信任損害" in report
