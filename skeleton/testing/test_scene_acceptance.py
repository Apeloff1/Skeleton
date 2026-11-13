"""End-to-end acceptance of authored playable scenes and portable saves."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_acceptance import (
    accept_scene, cli, verify_acceptance,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, original_demo, simulate,
)


def test_demo_is_source_bound_playable_and_portable() -> None:
    world, _ = original_demo()
    report = accept_scene(world)
    assert report["status"] == "passed"
    assert report["release_qualified"] is False
    assert report["audit"]["coverage"] == "complete"
    assert not report["holds"]
    assert report["route_proof"]["phase"] == "won"
    assert report["ending_proofs"]["lost"]["phase"] == "lost"
    assert report["route_proof"]["portable_checksum"]
    assert verify_acceptance(json.loads(json.dumps(report))) == report


def test_acceptance_from_checkpoint_preserves_exact_start() -> None:
    world, actions = original_demo()
    partial = simulate(world, actions[:1])
    report = accept_scene(session=partial)
    assert report["status"] == "passed"
    assert report["start_session"] == partial
    assert report["route_proof"]["journal_length"] > len(partial["journal"])
    assert verify_acceptance(report) == report


def test_authored_unreachable_scene_fails_acceptance() -> None:
    world, _ = original_demo()
    world["scenes"].append({
        "id": "orphan", "ending": None, "pickups": [], "exits": [],
    })
    report = accept_scene(world)
    assert report["status"] == "failed"
    assert report["holds"] == ["unobserved_scenes"]
    assert verify_acceptance(report) == report


def test_tiny_search_budget_is_inconclusive_not_failed() -> None:
    world, _ = original_demo()
    report = accept_scene(world, max_states=1)
    assert report["status"] == "inconclusive"
    assert report["holds"] == ["search_budget_exhausted"]
    assert verify_acceptance(report) == report


@pytest.mark.parametrize("field,change", [
    ("status", "passed"),
    ("source_digest", "0" * 64),
    ("report_digest", "0" * 64),
    ("release_qualified", True),
    ("holds", []),
    ("ending_proofs", {}),
    ("victory_route", {}),
])
def test_tampered_report_is_never_trusted(field, change) -> None:
    world, _ = original_demo()
    report = accept_scene(world, max_states=1)
    forged = copy.deepcopy(report)
    forged[field] = change
    with pytest.raises(SceneTravelError):
        verify_acceptance(forged)


def test_rejects_tampered_checkpoint_before_any_acceptance() -> None:
    world, actions = original_demo()
    partial = simulate(world, actions[:1])
    partial["state"]["inventory"] = ["forged_key"]
    with pytest.raises(SceneTravelError):
        accept_scene(session=partial)


@pytest.mark.parametrize("states,depth", [
    (True, 64), (0, 64), (4097, 64), (128, True),
    (128, 0), (128, 513),
])
def test_budget_is_strict(states, depth) -> None:
    world, _ = original_demo()
    with pytest.raises(SceneTravelError, match="budget"):
        accept_scene(world, max_states=states, max_depth=depth)


def test_cli_and_installed_main_check_verify(capsys) -> None:
    from skeleton.__main__ import main
    assert main(["scene-accept", "check", "--demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_cli_exposes_nonzero_inconclusive_and_invalid(capsys) -> None:
    assert cli(["check", "--demo", "--max-states", "1"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "inconclusive"
    assert cli(["verify", "--report-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_authored_reordering_is_deterministic() -> None:
    world, _ = original_demo()
    reversed_world = copy.deepcopy(world)
    reversed_world["scenes"].reverse()
    for scene in reversed_world["scenes"]:
        scene["pickups"].reverse()
        scene["exits"].reverse()
    assert accept_scene(world) == accept_scene(reversed_world)
