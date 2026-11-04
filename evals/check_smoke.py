#!/usr/bin/env python3
"""Recheck saved genuine smoke-test artifacts; this does not spawn agents."""

import json
from datetime import datetime

from council_checks import (ROOT, check_verification, lock_round, tally,
                            verification_candidates)


def read(path):
    return json.loads(path.read_text())


def main():
    folder = ROOT / "evals/results/smoke"
    audit = read(folder / "audit.json")
    packet = read(ROOT / "evals/fixtures/critical_flaw.packet.json")
    original = read(folder / "round_one.lock.json")
    reviews = [read(folder / (a + ".json")) for a in audit["planned_reviewers"]]
    locked = lock_round(packet, reviews)
    assert locked.sha256 == original["sha256"] == audit["round_one_sha256"]
    assert locked.reviews == original["reviews"]
    assert locked.packet == original["packet"]
    assert tally(locked) == original["tally"]
    assert verification_candidates(locked) == original["verification_candidates"]
    verifier = read(folder / "V02.json")
    check_verification(packet, verifier, ["C01", "C02", "C03"])
    assert len(audit["review_dispatches"]) == len(reviews) == 3
    assert {d["agent_id"] for d in audit["review_dispatches"]} == set(audit["planned_reviewers"])
    assert len({d["native_agent_path"] for d in audit["review_dispatches"]}) == 3
    assert all(d["fork_turns"] == "none" for d in audit["review_dispatches"])
    assert audit["verification_dispatch"]["fork_turns"] == "none"
    assert audit["verification_dispatch"]["agent_id"] == "V02"
    assert datetime.fromisoformat(audit["verification_validation_at"]) > datetime.fromisoformat(
        audit["round_one_locked_at"])
    assert not audit["failed_attempts"]
    report = (folder / "report.md").read_text()
    for section in ("01 — Executive Verdict", "02 — Council Voting",
                    "03 — Strongest Supporting Arguments", "04 — Strongest Opposing Arguments",
                    "05 — Critical Risks", "06 — Evidence Verification", "07 — Alternatives",
                    "08 — Recommended Next Steps", "09 — Audit Summary"):
        assert "## " + section in report
    assert "NOT_RECOMMEND" in report
    print("PASS: 3 genuine reviews + V02 validated; locked hash and tally unchanged")
    print("PASS: smoke provenance consistency and nine-section report structure")
    print("LIMIT: saved artifacts support replay checks, not independent proof of native execution")


if __name__ == "__main__":
    main()
