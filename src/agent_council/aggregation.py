"""純函式計票；失敗、缺件與棄權各自保留。"""

from collections import Counter, defaultdict
from collections.abc import Iterable

from .domain import PHASES, CouncilError, Json, Vote


def count_votes(outputs: Iterable[Json], expected_ids: set[str]) -> Json:
    by_id: dict[str, Json] = {}
    counts = dict.fromkeys((v.value for v in Vote), 0)
    for output in outputs:
        agent = output["agent_id"]
        if agent in by_id:
            raise CouncilError(f"重複陪審員：{agent}")
        if agent not in expected_ids:
            raise CouncilError(f"未知陪審員：{agent}")
        try:
            vote = Vote(output["vote"])
        except ValueError as exc:
            raise CouncilError(f"無效票種：{agent}") from exc
        counts[vote.value] += 1
        by_id[agent] = output
    valid_count = len(by_id)
    # 多數要求超過有效輸出的一半；棄權仍是有效輸出但不能形成建議。
    majority = next((v for v, n in counts.items() if n > valid_count / 2), None)
    if majority == Vote.ABSTAIN:
        majority = None
    highest = max(counts.values(), default=0)
    leaders = [v for v, n in counts.items() if n == highest and n > 0]
    return {
        "counts": counts,
        "valid_count": valid_count,
        "missing": sorted(expected_ids - set(by_id)),
        "majority": majority,
        "leading_votes": leaders,
    }


def aggregate(state: Json, roles: Json) -> Json:
    expected = {r["id"] for r in roles["jurors"]}
    records = state["records"]

    def outputs(phase: str) -> list[Json]:
        return [
            r["response"]["output"]
            for key, r in records.items()
            if key.startswith(phase + ".") and r["status"] == "ok"
        ]

    initial = sorted(outputs("initial"), key=lambda o: o["agent_id"])
    final = sorted(outputs("final"), key=lambda o: o["agent_id"])
    initial_by_id = {o["agent_id"]: o for o in initial}
    first = count_votes(initial, expected)
    last = count_votes(final, expected)
    changes = []
    for output in final:
        previous = initial_by_id.get(output["agent_id"])
        changes.append(
            {
                "agent_id": output["agent_id"],
                "initial_vote": previous["vote"] if previous else None,
                "final_vote": output["vote"],
                "changed": previous["vote"] != output["vote"] if previous else None,
                "reason": output["change_reason"],
            }
        )
    majority = last["majority"]
    minority = [o for o in final if majority is None or o["vote"] != majority]
    assumptions: dict[str, list[str]] = defaultdict(list)
    gaps: dict[str, list[str]] = defaultdict(list)
    for output in final:
        for a in sorted(set(output["assumptions"])):
            assumptions[a].append(output["agent_id"])
        for gap in sorted(set(output["evidence_gaps"])):
            gaps[gap].append(output["agent_id"])
    debate_missing = [
        f"{p}.{a}"
        for p in ("opening", "rebuttal")
        for a in ("pro", "con")
        if records.get(f"{p}.{a}", {}).get("status") != "ok"
    ]
    phase_missing = [phase for phase in PHASES if phase not in state.get("phase_log", [])]
    failures = [
        {"task_id": key, "errors": r["errors"]}
        for key, r in records.items()
        if r["status"] == "failed"
    ]
    # 不同票種標示需要比較的觀點，不把語意推斷偽裝成自動事實。
    by_vote = Counter(o["vote"] for o in final)
    return {
        "initial": first,
        "final": last,
        "changes": changes,
        "minority_ids": [o["agent_id"] for o in minority],
        "assumptions": dict(assumptions),
        "evidence_gaps": dict(gaps),
        "shared_assumptions": {a: ids for a, ids in assumptions.items() if len(ids) > 6},
        "disputed_assumptions": [
            {"agent_id": o["agent_id"], **entry}
            for o in final
            for entry in o.get("disputed_assumptions", [])
        ],
        "contradictions": [
            {"agent_id": o["agent_id"], **entry}
            for o in final
            for entry in o.get("contradictions", [])
        ],
        "assumption_perspectives": [
            {"agent_id": o["agent_id"], "vote": o["vote"], "assumptions": o["assumptions"]}
            for o in final
        ]
        if len(by_vote) > 1
        else [],
        "debate_missing": debate_missing,
        "failures": failures,
        "phase_missing": phase_missing,
        "complete": not first["missing"]
        and not last["missing"]
        and not debate_missing
        and not phase_missing,
        "consensus_is_proof": False,
    }
