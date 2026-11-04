"""Behavioral contract tests using SYNTHETIC review fixtures, never fake runs."""

import copy
import json
import unittest

from council_checks import (ROOT, check_packet, check_review, check_verification,
                            lock_round, tally, verification_candidates)

DIMENSIONS = ("value", "feasibility", "cost_efficiency", "risk_safety",
              "reversibility", "evidence_quality")
ROLES = ["Advocate", "Skeptic", "Risk Analyst", "Feasibility Analyst",
         "Economic Analyst", "Human Analyst", "Innovator", "Domain Specialist"]


def packet(name="embedded_linux"):
    return json.loads((ROOT / "evals/fixtures" / (name + ".packet.json")).read_text())


def review(p, number=1):
    """Synthetic input for contracts only; not a subagent judgment."""
    rec = {"kind": "SINGLE", "option_id": p["primary_option_id"], "vote": "SUPPORT",
           "conditions": [], "information_gaps": [], "rationale": "合成測試理由"}
    if p["evaluation_mode"] == "COMPARISON":
        rec = {"kind": "COMPARISON", "rankings": [
            {"rank": i + 1, "option_ids": [o["id"]], "rationale": "合成測試理由"}
            for i, o in enumerate(p["options"])],
            "preferred_option_ids": [p["options"][0]["id"]],
            "comparability": "COMPARABLE", "conditions": [],
            "information_gaps": [], "rationale": "合成測試理由"}
    return {
        "schema_version": "1.0", "request_id": p["request_id"],
        "agent_id": "A%02d" % number, "role": ROLES[number - 1],
        "specialty": p["domain_specialty"] if number == 8 else None,
        "recommendation": rec, "confidence": {"level": "MEDIUM", "rationale": "合成測試"},
        "key_strengths": [], "key_weaknesses": [], "critical_risks": [],
        "assumptions": [], "evidence": [], "alternatives": [],
        "what_would_change_my_mind": ["取得相反證據"],
        "scores": {o["id"]: {d: {"score": 3, "rationale": "合成測試"}
                             for d in DIMENSIONS} for o in p["options"]},
        "verification_flags": {"core_evidence_insufficient": False,
                               "disputed_claims": [], "decision_reversing_claims": []},
    }


def evidence(kind="INFERENCE"):
    return {"id": "E01", "claim": "合成因果證據", "kind": kind, "source": None,
            "locator": None, "observed_at": None,
            "verification": "NOT_APPLICABLE" if kind == "INFERENCE" else "UNVERIFIED"}


def add_risk(r, grounding="SUPPORTED", severity="CRITICAL"):
    r["evidence"] = [evidence()]
    r["critical_risks"] = [{"id": "R01", "description": "合成風險",
        "severity": severity, "irreversible": True, "grounding": grounding,
        "basis": "合成因果鏈", "evidence_ids": ["E01"], "mitigations": ["先驗證回復"]}]


def verification(p):
    return {"schema_version": "1.0", "request_id": p["request_id"],
            "agent_id": "V02", "role": "Risk Auditor", "findings": [{
                "claim_id": "C01", "claim": "合成主張", "status": "CONFIRMED",
                "rationale": "合成因果推論", "evidence_ids": ["E01"],
                "decision_impact": "先緩解風險", "limitations": ["僅測試"]}],
            "evidence": [evidence()], "limitations": ["合成測試"]}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.p = packet()
        self.r = review(self.p)

    def reject_review(self, mutate, p=None):
        mutate(self.r)
        with self.assertRaises(ValueError):
            check_review(p or self.p, self.r)

    def test_four_problem_fixtures_and_all_roles(self):
        for name in ("embedded_linux", "product_idea", "option_comparison", "critical_flaw"):
            p = packet(name)
            check_packet(p)
            for number in range(1, 9):
                check_review(p, review(p, number))

    def test_wrong_role_rejected(self):
        self.reject_review(lambda r: r.update(role="Skeptic"))

    def test_wrong_request_rejected(self):
        self.reject_review(lambda r: r.update(request_id="other"))

    def test_domain_specialty_must_match(self):
        r = review(self.p, 8)
        r["specialty"] = "Other specialty"
        with self.assertRaises(ValueError):
            check_review(self.p, r)

    def test_verifier_cannot_vote(self):
        self.reject_review(lambda r: r.update(agent_id="V01"))

    def test_extra_fields_rejected(self):
        self.reject_review(lambda r: r.update(success_probability=0.9))

    def test_confidence_not_probability(self):
        self.reject_review(lambda r: r.update(confidence={"level": 0.9, "rationale": "test"}))

    def test_conditional_support_requires_condition(self):
        self.reject_review(lambda r: r["recommendation"].update(vote="CONDITIONAL_SUPPORT"))

    def test_insufficient_information_requires_gap(self):
        self.reject_review(lambda r: r["recommendation"].update(vote="INSUFFICIENT_INFORMATION"))

    def test_wrong_primary_option(self):
        self.reject_review(lambda r: r["recommendation"].update(option_id="B0"))

    def test_score_bounds_and_types(self):
        for value in (0, 6, 2.5, True, None):
            r = copy.deepcopy(self.r)
            r["scores"]["P1"]["value"]["score"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_review(self.p, r)

    def test_na_is_valid_but_requires_reason(self):
        self.r["scores"]["P1"]["cost_efficiency"]["score"] = "N/A"
        check_review(self.p, self.r)
        self.reject_review(lambda r: r["scores"]["P1"]["cost_efficiency"].update(rationale=""))

    def test_all_options_and_dimensions_required(self):
        self.reject_review(lambda r: r["scores"].pop("B0"))
        r = review(self.p)
        r["scores"]["P1"].pop("value")
        with self.assertRaises(ValueError):
            check_review(self.p, r)

    def test_source_evidence_needs_locator_and_date(self):
        self.r["evidence"] = [evidence("SOURCE")]
        with self.assertRaises(ValueError):
            check_review(self.p, self.r)

    def test_invalid_source_date_rejected(self):
        self.r["evidence"] = [{**evidence("SOURCE"), "source": "test source",
            "locator": "https://example.invalid/fixture", "observed_at": "2026-02-30"}]
        with self.assertRaises(ValueError):
            check_review(self.p, self.r)

    def test_assumption_cannot_be_verified(self):
        self.r["evidence"] = [{**evidence("ASSUMPTION"), "verification": "VERIFIED"}]
        with self.assertRaises(ValueError):
            check_review(self.p, self.r)

    def test_missing_risk_evidence_rejected(self):
        add_risk(self.r)
        self.r["evidence"] = []
        with self.assertRaises(ValueError):
            check_review(self.p, self.r)

    def test_duplicate_evidence_id_rejected(self):
        self.r["evidence"] = [evidence(), evidence()]
        with self.assertRaises(ValueError):
            check_review(self.p, self.r)

    def test_duplicate_packet_option_rejected(self):
        self.p["options"].append(copy.deepcopy(self.p["options"][0]))
        with self.assertRaises(ValueError):
            check_packet(self.p)

    def test_comparison_cannot_use_binary_vote(self):
        p = packet("option_comparison")
        r = review(p)
        r["recommendation"] = self.r["recommendation"]
        with self.assertRaises(ValueError):
            check_review(p, r)

    def test_comparison_ties_are_counted_transparently(self):
        p = packet("option_comparison")
        r = review(p)
        r["recommendation"]["rankings"] = [
            {"rank": 1, "option_ids": ["P1", "P2"], "rationale": "合成並列"},
            {"rank": 2, "option_ids": ["B0"], "rationale": "合成理由"}]
        r["recommendation"]["preferred_option_ids"] = ["P1", "P2"]
        counts = tally(lock_round(p, [r]))
        self.assertEqual(counts["first_choice_inclusions"], {"P1": 1, "P2": 1, "B0": 0})
        self.assertEqual(counts["tied_first_reviewers"], 1)

    def test_comparison_missing_or_duplicate_option_rejected(self):
        p = packet("option_comparison")
        for bad_ids in (["P1"], ["P1", "P1", "P2", "B0"], ["P1", "P2", "X"]):
            r = review(p)
            r["recommendation"]["rankings"] = [{"rank": 1, "option_ids": bad_ids,
                                                   "rationale": "合成錯誤"}]
            with self.subTest(ids=bad_ids), self.assertRaises(ValueError):
                check_review(p, r)

    def test_comparison_non_dense_rank_rejected(self):
        p = packet("option_comparison")
        r = review(p)
        r["recommendation"]["rankings"][1]["rank"] = 3
        with self.assertRaises(ValueError):
            check_review(p, r)

    def test_comparison_preference_must_match_first_rank(self):
        p = packet("option_comparison")
        r = review(p)
        r["recommendation"]["preferred_option_ids"] = ["P2"]
        with self.assertRaises(ValueError):
            check_review(p, r)

    def test_comparison_may_abstain_without_fake_ranking(self):
        p = packet("option_comparison")
        r = review(p)
        r["recommendation"].update(comparability="INSUFFICIENT_INFORMATION",
            rankings=[], preferred_option_ids=[], information_gaps=["關鍵需求未知"])
        counts = tally(lock_round(p, [r]))
        self.assertEqual(counts["incomparable_reviewers"], 1)
        self.assertEqual(sum(counts["first_choice_inclusions"].values()), 0)

    def test_missing_agent_is_not_an_abstention(self):
        locked = lock_round(self.p, [review(self.p, i) for i in range(1, 8)])
        counts = tally(locked)
        self.assertEqual(counts["valid_reviewers"], 7)
        self.assertEqual(counts["missing_roles"], ["A08"])
        self.assertEqual(counts["votes"]["INSUFFICIENT_INFORMATION"], 0)

    def test_zero_valid_votes(self):
        self.assertEqual(sum(tally(lock_round(self.p, []))["votes"].values()), 0)

    def test_duplicate_retry_cannot_double_count(self):
        with self.assertRaises(ValueError):
            lock_round(self.p, [self.r, copy.deepcopy(self.r)])

    def test_round_snapshot_resists_later_mutation(self):
        locked = lock_round(self.p, [self.r])
        digest = locked.sha256
        self.r["recommendation"]["vote"] = "OPPOSE"
        locked.reviews[0]["recommendation"]["vote"] = "OPPOSE"
        self.assertEqual(locked.sha256, digest)
        self.assertEqual(tally(locked)["votes"]["SUPPORT"], 1)

    def test_seven_support_one_grounded_risk_triggers_audit(self):
        reviews = [review(self.p, i) for i in range(1, 9)]
        reviews[-1]["recommendation"]["vote"] = "OPPOSE"
        add_risk(reviews[-1])
        locked = lock_round(self.p, reviews)
        self.assertEqual(tally(locked)["votes"]["SUPPORT"], 7)
        self.assertEqual(verification_candidates(locked)["agents"], ["V02"])

    def test_three_evidence_gaps_trigger_verifier(self):
        reviews = [review(self.p, i) for i in range(1, 4)]
        for r in reviews:
            r["verification_flags"]["core_evidence_insufficient"] = True
        self.assertEqual(verification_candidates(lock_round(self.p, reviews))["agents"], ["V01"])
        self.assertEqual(verification_candidates(lock_round(self.p, reviews[:2]))["agents"], [])

    def test_high_stakes_triggers_even_without_valid_votes(self):
        p = packet("critical_flaw")
        self.assertEqual(verification_candidates(lock_round(p, []))["agents"], ["V02"])

    def test_value_disagreement_alone_skips_verification(self):
        other = review(self.p, 2)
        other["recommendation"]["vote"] = "OPPOSE"
        self.assertEqual(verification_candidates(lock_round(self.p, [self.r, other]))["agents"], [])

    def test_hypothetical_major_risk_alone_not_fact_trigger(self):
        add_risk(self.r, grounding="HYPOTHETICAL")
        self.assertEqual(verification_candidates(lock_round(self.p, [self.r]))["agents"], [])

    def test_material_conflict_and_reversing_dispute_trigger(self):
        locked = lock_round(self.p, [self.r])
        for flags in ({"factual_conflict": True}, {"decision_reversing_dispute": True}):
            self.assertEqual(verification_candidates(locked, **flags)["agents"], ["V01"])

    def test_verification_can_be_unresolved_without_tools(self):
        v = verification(self.p)
        v["evidence"] = []
        v["findings"][0].update(status="UNRESOLVED", evidence_ids=[])
        check_verification(self.p, v, ["C01"])

    def test_resolved_verification_needs_grounding(self):
        v = verification(self.p)
        v["evidence"] = [evidence("ASSUMPTION")]
        with self.assertRaises(ValueError):
            check_verification(self.p, v)

    def test_verification_claim_coverage(self):
        v = verification(self.p)
        check_verification(self.p, v, ["C01"])
        with self.assertRaises(ValueError):
            check_verification(self.p, v, ["C01", "C02"])

    def test_verification_does_not_change_locked_votes(self):
        locked = lock_round(self.p, [self.r])
        digest, counts = locked.sha256, tally(locked)
        check_verification(self.p, verification(self.p))
        self.assertEqual((locked.sha256, tally(locked)), (digest, counts))


if __name__ == "__main__":
    unittest.main()
