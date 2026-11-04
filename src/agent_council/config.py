"""安全載入 YAML、角色、設定與封裝資源。"""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from .domain import CouncilError, Json

RESOURCE = files("agent_council").joinpath("data")
REQUIRED_JURORS = frozenset(
    {
        "software_engineer",
        "entrepreneur",
        "investor",
        "economist",
        "psychologist",
        "scientist",
        "risk_analyst",
        "consumer",
        "ethicist",
        "legal_expert",
        "product_manager",
        "skeptic",
    }
)


def resource_text(name: str) -> str:
    return RESOURCE.joinpath(name).read_text(encoding="utf-8")


def load_document(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise CouncilError("YAML 格式錯誤，請檢查縮排與資料型別") from exc


def load_roles(path: Path | None = None) -> Json:
    data = load_document(path) if path else yaml.safe_load(resource_text("roles.yaml"))
    from .validation import validate

    validate(data, "roles")
    jurors = [r["id"] for r in data["jurors"]]
    if len(set(jurors)) != len(jurors):
        raise CouncilError("角色設定含重複陪審員 ID")
    if set(jurors) != REQUIRED_JURORS:
        raise CouncilError("角色設定必須包含指定的十二位陪審員")
    if {r["id"] for r in data["debaters"]} != {"pro", "con"}:
        raise CouncilError("正反代理必須各有一位")
    return data


def load_settings(path: Path | None = None) -> Json:
    data = load_document(path) if path else yaml.safe_load(resource_text("settings.yaml"))
    from .validation import validate

    validate(data, "settings")
    return data


def schema(name: str) -> Json:
    return json.loads(resource_text(f"schemas/{name}.json"))
