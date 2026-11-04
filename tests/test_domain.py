from copy import deepcopy

import pytest

from agent_council.aggregation import count_votes
from agent_council.config import load_roles, load_settings, schema
from agent_council.domain import CouncilError
from agent_council.storage import encode
from agent_council.validation import validate, validate_output

IDS = {"scientist", "skeptic"}


def test_roles_have_required_professional_contracts(roles):
    assert len(roles["jurors"]) == 12
    assert {r["id"] for r in roles["debaters"]} == {"pro", "con"}
    for role in roles["jurors"] + roles["debaters"]:
        assert role["priorities"] and role["questions"] and role["blind_spots"]
        assert role["instructions"] and role["output_schemas"]


def test_duplicate_role_rejected(tmp_path, roles):
    roles["jurors"][1]["id"] = roles["jurors"][0]["id"]
    path = tmp_path / "roles.yaml"
    path.write_text(encode(roles))
    with pytest.raises(CouncilError, match="重複"):
        load_roles(path)


def test_missing_role_rejected(tmp_path, roles):
    roles["jurors"].pop()
    path = tmp_path / "roles.yaml"
    path.write_text(encode(roles))
    with pytest.raises(CouncilError):
        load_roles(path)


@pytest.mark.parametrize("data", [None, {}, {"title": "只有標題"}])
def test_invalid_intake(data):
    with pytest.raises(CouncilError):
        validate(data, "idea")


def test_no_missing_facts_are_invented(fixture):
    idea = deepcopy(fixture["idea"])
    idea.update(context="", goals=[], constraints=[])
    validate(idea, "idea")
    assert idea["context"] == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("vote", "YES"),
        ("confidence", 0),
        ("confidence", True),
        ("confidence", 6),
        ("concerns", ["不足三項"]),
        ("agent_id", ""),
    ],
)
def test_invalid_vote_and_fields(fixture, field, value):
    output = fixture["responses"]["initial.scientist"]
    output[field] = value
    with pytest.raises(CouncilError):
        validate(output, "initial")


@pytest.mark.parametrize("vote", ["SUPPORT", "OPPOSE", "CONDITIONAL", "ABSTAIN"])
def test_vote_options(vote):
    result = count_votes([{"agent_id": "scientist", "vote": vote}], IDS)
    assert result["counts"][vote] == 1
    assert result["valid_count"] == 1
    assert result["missing"] == ["skeptic"]


def test_duplicate_juror_cannot_count():
    with pytest.raises(CouncilError, match="重複"):
        count_votes([{"agent_id": "scientist", "vote": "SUPPORT"}] * 2, IDS)


def test_unknown_juror_cannot_count():
    with pytest.raises(CouncilError, match="未知"):
        count_votes([{"agent_id": "someone", "vote": "SUPPORT"}], IDS)


def test_invalid_vote_cannot_count():
    with pytest.raises(CouncilError, match="無效"):
        count_votes([{"agent_id": "scientist", "vote": "yes"}], IDS)


def test_tie_is_not_majority():
    result = count_votes(
        [
            {"agent_id": "scientist", "vote": "SUPPORT"},
            {"agent_id": "skeptic", "vote": "CONDITIONAL"},
        ],
        IDS,
    )
    assert result["majority"] is None
    assert len(result["leading_votes"]) == 2


def test_abstention_cannot_be_recommendation():
    result = count_votes([{"agent_id": "scientist", "vote": "ABSTAIN"}], IDS)
    assert result["majority"] is None


def test_false_position_change_rejected(fixture):
    output = fixture["responses"]["final.scientist"]
    task = {
        "agent_id": "scientist",
        "phase": "final",
        "schema_name": "final",
        "output_schema": schema("final"),
        "payload": {"own_initial": fixture["responses"]["initial.scientist"]},
    }
    output["changed"] = False
    with pytest.raises(CouncilError, match="立場變動"):
        validate_output(task, output)


def test_missing_initial_requires_unknown_change(fixture):
    task = {
        "agent_id": "scientist",
        "phase": "final",
        "schema_name": "final",
        "output_schema": schema("final"),
        "payload": {"own_initial": None},
    }
    output = fixture["responses"]["final.scientist"]
    with pytest.raises(CouncilError):
        validate_output(task, output)
    output["changed"] = None
    validate_output(task, output)


def test_wrong_agent_id_rejected(fixture):
    task = {
        "agent_id": "skeptic",
        "phase": "initial",
        "schema_name": "initial",
        "output_schema": schema("initial"),
        "payload": {},
    }
    with pytest.raises(CouncilError, match="ID"):
        validate_output(task, fixture["responses"]["initial.scientist"])


@pytest.mark.parametrize("concurrency", [0, 13, True, "3"])
def test_bad_configuration(tmp_path, concurrency):
    path = tmp_path / "settings.yaml"
    path.write_text(encode({"backend": "native", "max_concurrency": concurrency, "max_retries": 1}))
    with pytest.raises(CouncilError):
        load_settings(path)


def test_unsafe_yaml_not_executed(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text('!!python/object/apply:os.system ["touch /tmp/never-execute"]')
    with pytest.raises(CouncilError, match="YAML"):
        load_settings(path)


def test_whitespace_title_rejected(fixture):
    fixture["idea"]["title"] = "   "
    with pytest.raises(CouncilError):
        validate(fixture["idea"], "idea")


def test_final_contradiction_cannot_reference_missing_material(fixture):
    output = fixture["responses"]["final.scientist"]
    output["contradictions"] = [
        {"sources": ["opening.pro", "opening.con"], "description": "不可引用缺件"}
    ]
    task = {
        "agent_id": "scientist",
        "phase": "final",
        "schema_name": "final",
        "output_schema": schema("final"),
        "payload": {
            "own_initial": fixture["responses"]["initial.scientist"],
            "debate": {"opening.pro": None, "opening.con": None},
        },
    }
    with pytest.raises(CouncilError, match="引用"):
        validate_output(task, output)
