from agent_council.cli import main
from agent_council.storage import Store


def test_cli_demo_list_report_validate(tmp_path, capsys):
    root = tmp_path / "results"
    common = ["--results", str(root)]
    assert main(common + ["validate"]) == 0
    assert main(common + ["demo"]) == 0
    summary = Store(root).summaries()[0]
    assert main(common + ["list"]) == 0
    assert main(common + ["report", summary["evaluation_id"]]) == 0
    text = capsys.readouterr().out
    assert "確定性模擬" in text and "十二" in text
    assert main(common + ["report", "unknown"]) == 2


def test_cli_native_workflow(tmp_path, capsys):
    root = tmp_path / "results"
    common = ["--results", str(root)]
    assert main(common + ["run", "ideas/examples/example.yaml"]) == 0
    eid = Store(root).summaries()[0]["evaluation_id"]
    assert main(common + ["native", "tasks", eid]) == 0
    assert main(common + ["native", "task", eid, "initial.scientist"]) == 0
    assert main(common + ["native", "prompt", eid]) == 0
    assert main(common + ["report", eid]) == 2
    assert main(common + ["native", "task", eid, "../../outside"]) == 2
    assert "fork_turns=none" in capsys.readouterr().out


def test_malformed_yaml_has_localized_error(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_text("title: [broken")
    assert main(["run", str(path)]) == 2
    assert "YAML 格式錯誤" in capsys.readouterr().err
