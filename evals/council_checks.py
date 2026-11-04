"""Offline QA helpers. No model calls, delegation, persistence, or orchestration."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
ROLE_NAMES = dict(zip(
    ["A%02d" % i for i in range(1, 9)],
    ["advocate", "skeptic", "risk_analyst", "feasibility", "economist",
     "human_analyst", "innovator", "domain_specialist"],
))
SCHEMAS = {
    p.stem.replace(".schema", ""): json.loads(p.read_text())
    for p in (ROOT / "schemas").glob("*.schema.json")
}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)


def validate_json(kind, instance):
    validator = Draft202012Validator(
        SCHEMAS[kind], registry=REGISTRY, format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: str(e.absolute_path))
    if errors:
        raise ValueError("; ".join(
            "%s: %s" % ("/".join(map(str, e.absolute_path)) or "$", e.message)
            for e in errors
        ))


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError("duplicate " + label)


def check_packet(packet):
    validate_json("review_packet", packet)
    ids = [o["id"] for o in packet["options"]]
    unique(ids, "option ID")
    unique([f["id"] for f in packet["known_facts"]], "fact ID")
    unique([c["dimension"] for c in packet["criteria"]], "criterion")
    if sum(o["status_quo"] for o in packet["options"]) > 1:
        raise ValueError("at most one status-quo baseline")
    if packet["evaluation_mode"] == "SINGLE" and packet["primary_option_id"] not in ids:
        raise ValueError("primary option absent from packet")


def check_evidence_refs(evidence, objects):
    evidence_ids = [e["id"] for e in evidence]
    unique(evidence_ids, "evidence ID")
    for item in objects:
        if not set(item["evidence_ids"]).issubset(evidence_ids):
            raise ValueError("unknown evidence reference")


def check_review(packet, review):
    check_packet(packet)
    validate_json("review_result", review)
    if review["request_id"] != packet["request_id"]:
        raise ValueError("request_id mismatch")
    if review["agent_id"] == "A08" and review["specialty"] != packet["domain_specialty"]:
        raise ValueError("domain specialty mismatch")
    ids = {o["id"] for o in packet["options"]}
    if set(review["scores"]) != ids:
        raise ValueError("scores must cover exactly all packet options")
    rec = review["recommendation"]
    if rec["kind"] != packet["evaluation_mode"]:
        raise ValueError("recommendation mode mismatch")
    if rec["kind"] == "SINGLE":
        if rec["option_id"] != packet["primary_option_id"]:
            raise ValueError("single vote targets the wrong option")
    elif rec["comparability"] != "INSUFFICIENT_INFORMATION":
        rankings = rec["rankings"]
        ranked = [i for group in rankings for i in group["option_ids"]]
        unique(ranked, "ranked option")
        if set(ranked) != ids:
            raise ValueError("ranking must cover exactly all packet options")
        if [g["rank"] for g in rankings] != list(range(1, len(rankings) + 1)):
            raise ValueError("ranks must be dense and ordered from 1")
        if set(rec["preferred_option_ids"]) != set(rankings[0]["option_ids"]):
            raise ValueError("preferred options must equal first rank group")
    unique([r["id"] for r in review["critical_risks"]], "risk ID")
    check_evidence_refs(review["evidence"], review["critical_risks"])
    for risk in review["critical_risks"]:
        if risk["grounding"] == "SUPPORTED" and not risk["evidence_ids"]:
            raise ValueError("supported risk needs an evidence reference")


def check_verification(packet, result, assigned_claim_ids=None):
    check_packet(packet)
    validate_json("verification_result", result)
    if result["request_id"] != packet["request_id"]:
        raise ValueError("verification request_id mismatch")
    claim_ids = [f["claim_id"] for f in result["findings"]]
    unique(claim_ids, "claim ID")
    if assigned_claim_ids is not None and set(claim_ids) != set(assigned_claim_ids):
        raise ValueError("findings must cover exactly the assigned claims")
    check_evidence_refs(result["evidence"], result["findings"])
    evidence = {e["id"]: e for e in result["evidence"]}
    for finding in result["findings"]:
        if finding["status"] != "UNRESOLVED":
            grounding = [evidence[e] for e in finding["evidence_ids"]]
            if not any(e["kind"] in ("USER_PROVIDED", "INFERENCE") or
                       (e["kind"] == "SOURCE" and e["verification"] == "VERIFIED")
                       for e in grounding):
                raise ValueError("resolved finding lacks observed or inferential grounding")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LockedRound:
    """Immutable serialized snapshot; returned objects are detached copies."""

    packet_json: str
    review_json: tuple

    @property
    def packet(self):
        return json.loads(self.packet_json)

    @property
    def reviews(self):
        return [json.loads(r) for r in self.review_json]

    @property
    def sha256(self):
        payload = canonical({"packet": self.packet, "reviews": self.reviews})
        return hashlib.sha256(payload.encode()).hexdigest()


def lock_round(packet, reviews):
    check_packet(packet)
    reviews = list(reviews)
    for review in reviews:
        check_review(packet, review)
    unique([r["agent_id"] for r in reviews], "reviewer ID")
    return LockedRound(canonical(packet), tuple(
        canonical(r) for r in sorted(reviews, key=lambda r: r["agent_id"])
    ))


def tally(locked):
    reviews = locked.reviews
    result = {"valid_reviewers": len(reviews),
              "missing_roles": sorted(set(ROLE_NAMES) - {r["agent_id"] for r in reviews})}
    if locked.packet["evaluation_mode"] == "SINGLE":
        counts = Counter(r["recommendation"]["vote"] for r in reviews)
        result["votes"] = {v: counts[v] for v in (
            "SUPPORT", "CONDITIONAL_SUPPORT", "OPPOSE", "INSUFFICIENT_INFORMATION"
        )}
    else:
        preferences = [r["recommendation"]["preferred_option_ids"] for r in reviews]
        counts = Counter(i for preferred in preferences for i in preferred)
        result["first_choice_inclusions"] = {
            o["id"]: counts[o["id"]] for o in locked.packet["options"]
        }
        result["tied_first_reviewers"] = sum(len(p) > 1 for p in preferences)
        result["incomparable_reviewers"] = sum(not p for p in preferences)
    return result


def verification_candidates(locked, *, factual_conflict=False,
                            decision_reversing_dispute=False):
    """Conservative candidates; an orchestrator still checks facts/grounding."""
    reasons = []
    agents = set()
    reviews = locked.reviews
    if factual_conflict:
        reasons.append("material_factual_conflict")
        agents.add("V01")
    if sum(r["verification_flags"]["core_evidence_insufficient"] for r in reviews) >= 3:
        reasons.append("three_core_evidence_gaps")
        agents.add("V01")
    if any(risk["severity"] in ("HIGH", "CRITICAL") and
           risk["grounding"] == "SUPPORTED" and risk["evidence_ids"]
           for r in reviews for risk in r["critical_risks"]):
        reasons.append("grounded_major_risk")
        agents.add("V02")
    if locked.packet["high_stakes"]:
        reasons.append("high_stakes")
        agents.add("V02")
    if decision_reversing_dispute:
        reasons.append("decision_reversing_dispute")
        agents.add("V01")
    return {"agents": sorted(agents), "reasons": reasons,
            "requires_semantic_review": True}
