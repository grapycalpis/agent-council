#!/usr/bin/env python3
"""Validate local artifacts, or a supplied packet/review; never run a model."""

import argparse
import json
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib
from jsonschema import Draft202012Validator

from council_checks import (ROOT, ROLE_NAMES, SCHEMAS, check_packet,
                            check_review, check_verification)


def read_json(path):
    return json.loads(Path(path).read_text())


def validate_repository():
    for schema in SCHEMAS.values():
        Draft202012Validator.check_schema(schema)
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
    assert set(config) == {"sandbox_mode", "approval_policy", "agents"}
    assert config["sandbox_mode"] == "read-only"
    assert config["approval_policy"] == "on-request"
    assert config["agents"] == {
        "enabled": True, "max_concurrent_threads_per_session": 8,
        "default_subagent_reasoning_effort": "medium",
    }
    expected = set(ROLE_NAMES.values()) | {"fact_verifier", "risk_auditor"}
    files = list((ROOT / ".codex/agents").glob("*.toml"))
    assert {p.stem for p in files} == expected
    for path in files:
        agent = tomllib.loads(path.read_text())
        assert set(agent) == {"name", "description", "developer_instructions",
                              "model_reasoning_effort"}, path
        assert agent["name"] == path.stem
        assert agent["description"] and agent["developer_instructions"]
        expected_effort = "high" if path.stem in {
            "domain_specialist", "fact_verifier", "risk_auditor"
        } else "medium"
        assert agent["model_reasoning_effort"] == expected_effort
        assert "Never spawn subagents" in agent["developer_instructions"]
        assert "write\nrepository files" in agent["developer_instructions"]
    packets = list((ROOT / "evals/fixtures").glob("*.packet.json"))
    assert len(packets) >= 4
    for packet in packets:
        check_packet(read_json(packet))
    print("PASS: %d schemas, %d agent TOMLs, root config, %d neutral packets" %
          (len(SCHEMAS), len(files), len(packets)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--review", type=Path)
    group.add_argument("--verification", type=Path)
    args = parser.parse_args()
    if (args.review or args.verification) and not args.packet:
        parser.error("--review / --verification requires --packet")
    validate_repository()
    if args.packet:
        packet = read_json(args.packet)
        check_packet(packet)
        if args.review:
            check_review(packet, read_json(args.review))
        if args.verification:
            check_verification(packet, read_json(args.verification))
        print("PASS: supplied packet and result (if provided)")


if __name__ == "__main__":
    main()
