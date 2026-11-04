import subprocess
import sys
import tomllib
from pathlib import Path


def test_fifteen_official_standalone_agent_definitions():
    paths = list(Path(".codex/agents").glob("council_*.toml"))
    assert len(paths) == 15
    names = set()
    for path in paths:
        data = tomllib.loads(path.read_text())
        assert set(data) == {"name", "description", "developer_instructions"}
        assert data["name"] not in names
        names.add(data["name"])
        assert "繁體中文" in data["developer_instructions"]


def test_derived_agent_definitions_match_roles():
    subprocess.run([sys.executable, "scripts/generate_agents.py", "--check"], check=True)
