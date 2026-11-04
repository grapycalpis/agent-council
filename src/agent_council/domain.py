"""領域型別與版本化資料契約。"""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

Json = dict[str, Any]


class Vote(StrEnum):
    SUPPORT = "SUPPORT"
    OPPOSE = "OPPOSE"
    CONDITIONAL = "CONDITIONAL"
    ABSTAIN = "ABSTAIN"


PHASES = ("initial", "opening", "rebuttal", "final")
VOTE_LABELS = {"SUPPORT": "支持", "OPPOSE": "反對", "CONDITIONAL": "有條件支持", "ABSTAIN": "棄權"}
PHASE_LABELS = {
    "initial": "獨立初評",
    "opening": "正反開場",
    "rebuttal": "單輪反駁",
    "final": "最終評估",
}


@dataclass(frozen=True)
class Capabilities:
    name: str
    execution_kind: str
    independent_contexts: bool
    can_resume: bool
    external_evidence: bool
    model: str | None = None
    token_usage: int | None = None

    def snapshot(self) -> Json:
        return asdict(self)


@dataclass(frozen=True)
class Response:
    output: Json
    context_id: str
    model: str | None = None
    token_usage: int | None = None
    provenance: str = "mock"
    context_mode: str = "fresh"

    def snapshot(self) -> Json:
        return asdict(self)


class CouncilError(ValueError):
    """可向使用者顯示的驗證錯誤。"""


class PendingTask(Exception):
    """需要外部原生代理執行，不能當作失敗或棄權。"""
