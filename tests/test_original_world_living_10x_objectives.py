"""Evidence, warning, and adaptive progression director for living worlds."""
from __future__ import annotations
from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_living_10x_runtime import (
    LivingAction, create_living, step_living,
)
from skeleton.game.generation.original_world_living_10x_objectives import (
    living_objectives,
)
from skeleton.game.generation.original_world_living_10x_cli import main
from skeleton.game.generation.original_world_living_systems import SYSTEMS


def world(system):
    return create_living(living_for(0, "puzzle", "lattice", system, "endless").index)


def action(state, verb, layer="living"):
    return step_living(state, LivingAction(layer, verb))[0]


@pytest.mark.parametrize("system", [law.system_id for law in SYSTEMS])
def test_each_living_system_has_adaptive_material_goal_and_measured_evidence(system) -> None:
    state = world(system)
    before = asdict(state)
    report = living_objectives(state)
    assert report["living_system"] == system
    assert len(report["objectives"]) == 3
    assert not report["objectives"][0]["done"]
    assert not report["objectives"][1]["done"]
    assert not report["objectives"][2]["done"]
    assert report["next_action"].startswith("living ")
    assert report["no_native_game_claim"]
    assert not report["world_has_guaranteed_win"]
    assert asdict(state) == before
    progressed = action(state, SYSTEMS[
        next(i for i, s in enumerate(SYSTEMS) if s.system_id == system)
    ].commands[0])
    report2 = living_objectives(progressed)
    assert report2["objectives"][1]["done"]
    assert report2["objectives"][0]["done"] is False
    progressed = action(progressed, "end_turn", layer="causal")
    report3 = living_objectives(progressed)
    assert report3["objectives"][0]["done"]
    assert report3["objectives"][1]["done"]
    assert progressed.living_turns == 1


def test_crisis_detection_is_a_readonly_material_observation() -> None:
    s = world("settlement")
    s = replace(s, metrics=replace(s.metrics, food=0, unrest=8))
    report = living_objectives(s)
    assert report["warnings"][0]["severity"] == "critical"
    assert "stored food=0" in report["warnings"][0]["evidence"]
    assert report["next_action"] == "living ration"
    assert not report["locally_stable"]


def test_living_goals_do_not_claim_global_victory_for_unwinnable_arc() -> None:
    state = world("watershed")
    state = action(state, "irrigate")
    state = action(state, "end_turn", layer="causal")
    report = living_objectives(state)
    assert report["continuation"] == "unwinnable"
    assert not report["world_has_guaranteed_win"]
    assert report["objectives"][2]["done"]
    assert report["locally_stable"]


def test_autonomous_machine_wear_changes_recommendation_from_design_to_service() -> None:
    state = world("fabrication")
    before = living_objectives(state)
    assert before["next_action"] == "living service"
    state = action(state, "design")
    state = action(state, "end_turn", layer="causal")
    assert state.metrics.completed == 1
    assert state.metrics.wear == state.metrics.builders
    next_steps = living_objectives(state)
    assert next_steps["next_action"] == "living service"
    assert not next_steps["locally_stable"]
    state = action(state, "service")
    assert living_objectives(state)["locally_stable"]


def test_policy_director_reports_all_relevant_warnings_not_fake_advice() -> None:
    s = world("spores")
    s = replace(
        s, metrics=replace(s.metrics, unaffected=0, affected=10, remedies=0),
        spatial=replace(s.spatial, danger=25),
    )
    advice = living_objectives(s)
    assert len(advice["warnings"]) == 2
    assert {w["severity"] for w in advice["warnings"]} == {"critical", "warning"}
    assert advice["next_action"] == "living study"


def test_live_objectives_exposed_by_offline_cli(capsys) -> None:
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "watershed", "--arc", "endless",
        "--actions-json", '[{"layer":"living","verb":"irrigate"},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--objectives",
    ]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["objectives"]["locally_stable"]
    assert printed["objectives"]["objectives"][0]["done"]
    assert printed["objectives"]["next_action"]


def test_original_world_atlas_entrypoint_supports_old_and_new_namespace(capsys) -> None:
    from skeleton.game.generation.original_world_cli import main as old_main
    assert old_main(["--living-index", "122879999", "--brief"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["world"]["index"] == "122879999"
    assert preview["world"]["living_system"] == "echoes"
    assert preview["inventory"]["living_advanced_configurations"] == 122880000
    assert preview["world"]["provenance"].startswith("composed")
    assert "--index 122879999" in preview["play_command"]

    assert old_main(["--living-foundation-index", "10239999"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["foundation"]["index"] == "10239999"
    assert found["inventory"]["living_foundations"] == 10240000

    assert old_main(["--living-seed", "future-playable-dynasty", "--brief"]) == 0
    seeded = json.loads(capsys.readouterr().out)
    assert seeded["world"]["index"].isdigit()
