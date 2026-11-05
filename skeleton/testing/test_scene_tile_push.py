"""End-to-end playable push-block scene acceptance and security regression."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_push import (
    _step, cli, edit_push, export_push, import_push, legal_push_actions,
    new_push, normalize_push, original_push, resume_push, simulate_push,
    verify_push,
)
from skeleton.game.gameplay.scene_tile_push_solver import solve_push
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def demo():
    return original_push()


def test_player_pushes_crate_onto_plate_and_earns_canonical_ending(demo):
    source, actions = demo
    session = simulate_push(source, actions)
    assert session["state"]["phase"] == "won"
    assert session["state"]["crates"]["iron_block"]["at"] == [2, 1]
    assert session["state"]["tile"]["state"]["scene"]["state"]["phase"] == "won"
    assert len(session["journal"]) == len(actions)
    assert verify_push(session) == session
    assert import_push(export_push(session)) == session


def test_save_resume_equals_one_shot_play_and_is_deterministic(demo):
    source, actions = demo
    first = simulate_push(source, actions[:5])
    restored = import_push(export_push(first))
    resumed = resume_push(restored, actions[5:])
    assert resumed == simulate_push(source, actions)
    assert resumed["state_digest"] == dig(resumed["state"])
    assert resumed["save"]["state_digest"] == resumed["state_digest"]


def test_unearned_locked_exit_is_rejected_without_mutating_session(demo):
    source, _ = demo
    start = new_push(source)
    without_plate = copy.deepcopy(start)
    without_plate["state"]["crates"]["iron_block"]["at"] = [1, 2]
    # Forged crate state cannot bypass replay.
    with pytest.raises(SceneTravelError, match="replay"):
        verify_push(without_plate)
    # Walk to the exit via the bypass, without moving the crate.
    actions = [
        {"kind": "move", "direction": "south"},
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "east"},
        {"kind": "move", "direction": "north"},
        {"kind": "move", "direction": "east"},
    ]
    before = simulate_push(source, actions)
    with pytest.raises(SceneTravelError, match="inactive pressure plates"):
        _step(before, {"kind": "travel", "exit_id": "north"})
    assert verify_push(before) == before


def test_crate_cannot_be_pushed_into_wall_exit_or_another_crate(demo):
    source, _ = demo
    bad = copy.deepcopy(source)
    bad["crates"].append({"id": "second", "scene_id": "quay", "at": [2, 1]})
    start = new_push(bad)
    with pytest.raises(SceneTravelError, match="collision"):
        _step(start, {"kind": "move", "direction": "east"})
    assert verify_push(start) == start
    bad["crates"][1]["at"] = [4, 1]
    with pytest.raises(SceneTravelError, match="interaction"):
        normalize_push(bad)


@pytest.mark.parametrize("mutate", [
    lambda x: x["crates"][0].update(at=[0, 1]),
    lambda x: x["crates"][0].update(at=[0, 2]),
    lambda x: x["crates"][0].update(at=[1, 0]),
    lambda x: x["plates"][0].update(at=[99, 99]),
    lambda x: x["plates"].append(copy.deepcopy(x["plates"][0])),
    lambda x: x["locks"][0].update(requires_plates=["unknown"]),
    lambda x: x["locks"][0].update(exit_id="unknown"),
    lambda x: x.update(turn_limit=True),
    lambda x: x.update(schema_version="future"),
    lambda x: x["crates"].append(copy.deepcopy(x["crates"][0])),
])
def test_malformed_source_rejected(demo, mutate):
    source, _ = demo
    bad = copy.deepcopy(source)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        normalize_push(bad)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"]["crates"]["iron_block"].update(at=[3, 1]),
    lambda x: x["state"]["tile"]["state"].update(position=[4, 1]),
    lambda x: x["journal"][0]["action"].update(direction="west"),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(event_bus_digest="0" * 64),
    lambda x: x["save"].update(tick=999),
])
def test_tampered_saves_fail_closed(demo, mutate):
    source, actions = demo
    bad = copy.deepcopy(simulate_push(source, actions[:4]))
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_push(bad)


def test_portable_bundle_rejects_tamper_even_with_recomputed_checksum(demo):
    source, actions = demo
    bundle = export_push(simulate_push(source, actions[:4]))
    for field in ("checksum", "state_digest", "source_digest"):
        bad = copy.deepcopy(bundle)
        bad[field] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_push(bad)
    bad = copy.deepcopy(bundle)
    bad["session"]["state"]["crates"]["iron_block"]["at"] = [4, 1]
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError):
        import_push(bad)


def test_legal_actions_do_not_advertise_unearned_travel(demo):
    source, _ = demo
    start = new_push(source)
    assert {"kind": "move", "direction": "east"} in legal_push_actions(start)
    assert not any(a["kind"] == "travel" for a in legal_push_actions(start))
    moved = _step(start, {"kind": "move", "direction": "east"})
    assert moved["state"]["crates"]["iron_block"]["at"] == [2, 1]


def test_authoring_digest_lease_and_preview_are_atomic(demo):
    source, _ = demo
    normalized = normalize_push(source)
    edits = [{"kind": "relocate_plate", "id": "gate_plate",
              "scene_id": "quay", "at": [3, 1]}]
    result = edit_push(source, dig(normalized), edits, [])
    assert result["source"]["plates"][0]["at"] == [3, 1]
    assert result["preview"]["state"]["tick"] == 0
    assert source["plates"][0]["at"] == [2, 1]
    with pytest.raises(SceneTravelError, match="conflict"):
        edit_push(source, "0" * 64, edits)
    with pytest.raises(SceneTravelError):
        edit_push(source, dig(normalized), [
            {"kind": "relocate_crate", "id": "iron_block",
             "scene_id": "quay", "at": [0, 1]},
        ])
    assert normalize_push(source) == normalized


def test_solver_budget_is_explicit_and_witness_replays(demo):
    source, actions = demo
    limited = solve_push(source, max_states=1, max_depth=1)
    assert limited["status"] == "inconclusive"
    assert limited["budget_exhausted"] is True
    assert limited["final_state_digest"] is None
    # A solved source-bound checkpoint is itself a valid zero-action witness.
    won = simulate_push(source, actions)
    solved = solve_push(source, session=won, max_states=1, max_depth=1)
    assert solved["status"] == "found"
    assert solved["actions"] == []
    assert solved["final_state_digest"] == won["state_digest"]


def test_solver_refuses_source_mismatch(demo):
    source, _ = demo
    session = new_push(source)
    bad = copy.deepcopy(source)
    bad["turn_limit"] = 31
    with pytest.raises(SceneTravelError, match="mismatch"):
        solve_push(bad, session=session)


def test_cli_source_play_save_export_import_author_and_error(capsys, demo):
    from skeleton.__main__ import main
    assert main(["scene-push", "demo"]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["state"]["phase"] == "won"
    assert main(["scene-push", "export", "--session-json",
                 json.dumps(completed)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert main(["scene-push", "import", "--bundle-json",
                 json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == completed
    source, actions = demo
    assert cli(["simulate", "--source-json", json.dumps(source),
                "--actions-json", json.dumps(actions[:3])]) == 0
    checkpoint = json.loads(capsys.readouterr().out)
    assert cli(["resume", "--session-json", json.dumps(checkpoint),
                "--actions-json", json.dumps(actions[3:])]) == 0
    assert json.loads(capsys.readouterr().out) == completed
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_resource_bounds_and_invalid_action_rejected(demo):
    source, _ = demo
    source["turn_limit"] = 1
    start = new_push(source)
    advanced = _step(start, {"kind": "move", "direction": "east"})
    with pytest.raises(SceneTravelError, match="budget"):
        _step(advanced, {"kind": "move", "direction": "west"})
    with pytest.raises(SceneTravelError):
        _step(start, {"kind": "move", "direction": "diagonal"})
    with pytest.raises(SceneTravelError):
        _step(start, {"kind": "teleport", "at": [4, 1]})
    with pytest.raises(SceneTravelError):
        simulate_push(source, [{"kind": "move", "direction": "east"}] * 300)
