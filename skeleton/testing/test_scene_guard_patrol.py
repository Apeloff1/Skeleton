"""Guard patrol source→play→save/replay→export acceptance and failure paths."""
from __future__ import annotations

import copy
import io
import json
from contextlib import redirect_stdout, redirect_stderr

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_guard_patrol import (
    advance_patrol, export_patrol, import_patrol, inspect_patrol,
    new_patrol, normalize_patrol, original_patrol, simulate_patrol,
    verify_patrol,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_guard_patrol_can_be_played_and_exported():
    source = original_patrol()
    actions = [
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "travel", "exit_id": "north"},
        {"kind": "travel", "exit_id": "inside"},
    ]
    result = simulate_patrol(source, actions)
    assert result["state"]["phase"] == "won"
    assert result["state"]["scene"]["state"]["ending"] == "victory"
    assert verify_patrol(result) == result
    assert import_patrol(export_patrol(result)) == result
    assert simulate_patrol(source, actions) == result


def test_guard_blocks_travel_at_occupied_exit_and_wait_opens_route():
    source = original_patrol()
    first = advance_patrol(new_patrol(source), {"kind": "collect", "pickup_id": "find_key"})
    second = advance_patrol(first, {"kind": "wait"})
    before = copy.deepcopy(second)
    with pytest.raises(SceneTravelError, match="patrol blocks"):
        advance_patrol(second, {"kind": "travel", "exit_id": "north"})
    assert second == before
    third = advance_patrol(second, {"kind": "wait"})
    assert inspect_patrol(third)["guards"] == [{"guard_id": "harbor_watch", "scene_id": "gate"}]
    fourth = advance_patrol(third, {"kind": "travel", "exit_id": "north"})
    fifth = advance_patrol(fourth, {"kind": "travel", "exit_id": "inside"})
    assert fifth["state"]["phase"] == "won"


def test_replay_resume_and_source_mismatch():
    source = original_patrol()
    first = advance_patrol(new_patrol(source), {"kind": "wait"})
    result = simulate_patrol(source, [
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "wait"},
        {"kind": "travel", "exit_id": "north"},
    ], resume=first)
    assert result == simulate_patrol(source, [
        {"kind": "wait"}, {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "wait"},
        {"kind": "travel", "exit_id": "north"},
    ])
    changed = copy.deepcopy(source)
    changed["patrol_id"] = "different"
    with pytest.raises(SceneTravelError, match="source mismatch"):
        simulate_patrol(changed, [], resume=result)


def test_invalid_guard_route_and_exit_rejected():
    source = original_patrol()
    for key, value in (
        ("route", ["quay", "sanctuary"]),
        ("route", ["quay", "quay"]),
        ("offset", True),
        ("offset", 3),
        ("bypass_item", "not_authored"),
        ("blocked_exits", [{"scene_id": "quay", "exit_id": "missing"}]),
    ):
        changed = copy.deepcopy(source)
        changed["guards"][0][key] = value
        with pytest.raises(SceneTravelError):
            normalize_patrol(changed)


def test_replayed_save_and_guard_cannot_be_forged():
    result = simulate_patrol(original_patrol(), [{"kind": "wait"}])
    cases = []
    forged = copy.deepcopy(result)
    forged["state"]["tick"] = 17
    cases.append(forged)
    forged = copy.deepcopy(result)
    forged["journal"][0]["action"]["kind"] = "travel"
    cases.append(forged)
    forged = copy.deepcopy(result)
    forged["save"]["parent_save_digest"] = "0" * 64
    cases.append(forged)
    forged = copy.deepcopy(result)
    forged["state"]["scene"]["state"]["inventory"].append("master_key")
    cases.append(forged)
    for case in cases:
        with pytest.raises(SceneTravelError):
            verify_patrol(case)


def test_bypass_item_is_earned_not_injected():
    source = original_patrol()
    source["guards"][0]["bypass_item"] = "brass_key"
    first = advance_patrol(new_patrol(source), {"kind": "collect", "pickup_id": "find_key"})
    second = advance_patrol(first, {"kind": "wait"})
    third = advance_patrol(second, {"kind": "travel", "exit_id": "north"})
    assert third["state"]["scene"]["state"]["scene_id"] == "gate"


def test_terminal_rejected_and_checksum_failure():
    source = original_patrol()
    finished = simulate_patrol(source, [
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "travel", "exit_id": "north"},
        {"kind": "travel", "exit_id": "inside"},
    ])
    with pytest.raises(SceneTravelError):
        advance_patrol(finished, {"kind": "wait"})
    bundle = export_patrol(finished)
    bundle["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        import_patrol(bundle)


def test_cli_demo_and_malformed_source():
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["scene-patrol", "demo"]) == 0
    assert verify_patrol(json.loads(output.getvalue()))["state"]["phase"] == "won"
    error = io.StringIO()
    with redirect_stderr(error):
        assert main(["scene-patrol", "new", "--source-json", '{"bad":true}']) == 2
    assert '"ok": false' in error.getvalue()
