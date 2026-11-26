"""Canonical original faction negotiation plans, CLI/Jeeves parity, and abuse paths."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_faction_plan import (
    PLAN_SCHEMA, plan_faction_negotiation,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    FACTION_PLAN_REQUEST_SCHEMA, execute_faction_plan_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def source():
    return read_blueprint(PROJECT)


def test_shortest_original_social_plan_is_replay_verified_and_immutable():
    docs = source()
    original = deepcopy(docs)
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    result = plan_faction_negotiation(
        docs, faction_id="residents", minimum=3,
        expected_source_digest=digest, authorized=True)
    assert docs == original
    assert result == plan_faction_negotiation(
        deepcopy(docs), faction_id="residents", minimum=3,
        expected_source_digest=digest, authorized=True)
    assert result["schema"] == PLAN_SCHEMA
    assert result["planned_decisions"] == ["neutral_audit", "publish_ledger"]
    assert result["resulting_reputation"]["residents"] == 3
    assert result["planned_decision_count"] == 2
    assert result["status"] == "simulatable"
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False


def test_continuation_and_already_met_goals():
    docs = source()
    next_step = plan_faction_negotiation(
        docs, faction_id="residents", minimum=3,
        decisions=["publish_ledger"], authorized=True)
    assert next_step["planned_decisions"] == ["neutral_audit"]
    assert next_step["history_decisions"] == ["publish_ledger"]
    assert next_step["resulting_reputation"]["residents"] == 3
    already = plan_faction_negotiation(
        docs, faction_id="residents", minimum=2,
        decisions=["publish_ledger"], authorized=True)
    assert already["planned_decisions"] == []
    assert already["status"] == "simulatable"
    opposite = plan_faction_negotiation(
        docs, faction_id="residents", maximum=-2, authorized=True)
    assert opposite["planned_decisions"] == ["private_deal"]


def test_unreachable_goal_never_mints_authored_effects():
    result = plan_faction_negotiation(
        source(), faction_id="claimants", minimum=5, authorized=True)
    assert result["status"] == "unreachable_within_budget"
    assert result["planned_decisions"] == []
    assert result["resulting_reputation"] == result["starting_reputation"]
    assert result["external_evidence_verified"] is False


def test_faction_planning_fails_closed_on_invalid_or_stale_inputs():
    docs = source()
    with pytest.raises(PermissionError):
        plan_faction_negotiation(docs, faction_id="residents",
                                 minimum=3, authorized=False)
    invalid = (
        {"faction_id": "absent", "minimum": 3},
        {"faction_id": "residents", "minimum": True},
        {"faction_id": "residents", "minimum": 101},
        {"faction_id": "residents", "minimum": 3, "maximum": 4},
        {"faction_id": "residents"},
        {"faction_id": "residents", "minimum": 3, "decisions": ["publish_ledger"] * 2},
        {"faction_id": "residents", "minimum": 3, "decisions": ["unwritten"]},
        {"faction_id": "residents", "minimum": 3, "expected_source_digest": "0" * 64},
    )
    for options in invalid:
        with pytest.raises(StudioQuestError):
            plan_faction_negotiation(docs, authorized=True, **options)
    mutated = deepcopy(docs)
    mutated["cast"]["social_rules"][0]["reputation_delta"]["residents"] = 100
    with pytest.raises(StudioQuestError):
        plan_faction_negotiation(
            mutated, faction_id="residents", minimum=3, authorized=True)


def test_cli_and_typed_jeeves_share_authoritative_plan(capsys):
    from scripts.studio_ecosystem_cli import main
    docs = source()
    digest = audit_canon_source(docs, authorized=True)["source_digest"]
    request = {
        "schema": FACTION_PLAN_REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": digest, "faction_id": "residents",
        "minimum": 3, "decisions": ["publish_ledger"],
    }
    with pytest.raises(PermissionError):
        execute_faction_plan_tool(request, authorized=False)
    typed = execute_faction_plan_tool(request, authorized=True)
    assert typed["file_write_performed"] is False
    assert main(["--project", PROJECT, "--faction-plan",
                 "--faction-goal", '{"faction_id":"residents","minimum":3}',
                 "--faction-decisions", '["publish_ledger"]',
                 "--faction-expected-digest", digest]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_faction_plan_tool({**request, "unknown": 1}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--faction-plan",
              "--faction-goal", '{"faction_id":"residents","minimum":3,"minimum":4}'])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--faction-goal", "{}"])
