"""Deterministic ending route plans from authoritative original quest source."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_ending_plan import plan_authored_ending
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest, start_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    ENDING_PLAN_REQUEST_SCHEMA, execute_ending_plan_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def test_unbound_original_ending_remains_blocked_but_plan_is_deterministic():
    source = read_blueprint(PROJECT)
    session = start_quest(source, authorized=True)
    original = deepcopy(session)
    plan = plan_authored_ending(
        source, ending_id="commons", session=session, authorized=True)
    assert plan == plan_authored_ending(
        source, ending_id="commons", session=session, authorized=True)
    assert plan["status"] == "blocked_external_predicates"
    assert plan["external_unbound_predicates"]
    assert plan["sandbox_eligible_after_plan"] is False
    assert plan["original_session_unchanged"] is True
    assert plan["release_certified"] is False
    assert session == original


def test_fully_bound_sandbox_ending_is_replayable_not_release_certified():
    source = read_blueprint(PROJECT)
    revised = deepcopy(source)
    revised["narrative"]["endings"][0]["requires"] = [
        revised["quest"]["stage_graph"][0]["reward"],
        revised["quest"]["stage_graph"][2]["reward"],
    ]
    plan = plan_authored_ending(revised, ending_id="commons", authorized=True)
    assert plan["status"] == "simulatable"
    assert plan["sandbox_eligible_after_plan"] is True
    assert plan["planned_stage_count"] == 3
    assert [s["stage_id"] for s in plan["planned_steps"]] == [
        "investigate", "intervene", "ratify"]
    actions = [[s["stage_id"], s["choice"]] for s in plan["planned_steps"]]
    replayed = replay_quest(revised, actions, authorized=True)
    resumed = plan_authored_ending(
        revised, ending_id="commons", session=replayed, authorized=True)
    assert resumed["planned_stage_count"] == 0
    assert resumed["sandbox_eligible_after_plan"] is True
    assert resumed["release_certified"] is False


def test_unknown_ending_forged_session_and_permission_are_rejected():
    source = read_blueprint(PROJECT)
    with pytest.raises(PermissionError):
        plan_authored_ending(source, ending_id="commons", authorized=False)
    with pytest.raises(StudioQuestError):
        plan_authored_ending(source, ending_id="nonexistent", authorized=True)
    other = read_blueprint("studio_puzzle_expedition_copper_mesa")
    forged = start_quest(other, authorized=True)
    with pytest.raises(StudioQuestError):
        plan_authored_ending(source, ending_id="commons",
                             session=forged, authorized=True)


def test_cli_and_typed_jeeves_endings_use_same_source(capsys):
    from scripts.studio_ecosystem_cli import main
    req = {"schema": ENDING_PLAN_REQUEST_SCHEMA,
           "project_id": PROJECT, "ending_id": "commons", "actions": []}
    with pytest.raises(PermissionError):
        execute_ending_plan_tool(req, authorized=False)
    result = execute_ending_plan_tool(req, authorized=True)
    assert result["detail"]["status"] == "blocked_external_predicates"
    assert main(["--project", PROJECT, "--ending-plan", "--ending-id", "commons",
                 "--quest-actions", "[]"]) == 0
    cli = json.loads(capsys.readouterr().out)
    assert cli == result["detail"]
    with pytest.raises(StudioQuestError):
        execute_ending_plan_tool({**req, "extra": True}, authorized=True)
