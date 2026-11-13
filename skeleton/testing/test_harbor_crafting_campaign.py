"""End-to-end acceptance and adversarial contracts for the original Lantern Quay game."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, MAX_SOURCE_BYTES, canonical, decode, demo_actions,
    digest, export_bundle, initial_state, load_source, run, step,
    validate_source, verify_bundle,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def won_bundle():
    return export_bundle(world(), demo_actions(), require_win=True)


def test_source_to_player_actions_to_victory_to_export_to_verified_replay():
    source = world()
    original = deepcopy(source)
    bundle = won_bundle()
    state = verify_bundle(decode(canonical(bundle)), require_win=True)
    assert state["ending"] == "beacon"
    assert state["delivered"] is True
    assert state["reputation"] == 3
    assert state["inventory"] == {}
    assert state["tick"] == len(demo_actions())
    assert state["pos"] == [5, 3]
    assert source == original
    assert bundle["source_digest"] == digest(source)
    assert bundle["terminal_digest"] == digest(state)
    assert len(bundle["events"]) == len(demo_actions())
    assert bundle["events"][-1]["after"] == digest(state)


def test_repeat_runs_are_bit_identical_across_save_export_and_replay():
    first = canonical(won_bundle())
    second = canonical(won_bundle())
    assert first == second
    assert canonical(export_bundle(world(), demo_actions())) == first
    assert verify_bundle(decode(first)) == verify_bundle(decode(second))


def test_shelter_choice_produces_distinct_earned_ending():
    actions = demo_actions()
    actions[-1] = {"op": "choose", "choice": "shelter"}
    alternative = export_bundle(world(), actions, require_win=True)
    assert verify_bundle(alternative, require_win=True)["ending"] == "safe_harbor"
    assert alternative["state"]["reputation"] == 2
    assert alternative["terminal_digest"] != won_bundle()["terminal_digest"]


def test_checkpoint_before_victory_is_portable_but_not_release_acceptance():
    partial = export_bundle(world(), demo_actions()[:-2])
    assert verify_bundle(partial)["ending"] is None
    with pytest.raises(HarborError, match="victory not earned"):
        verify_bundle(partial, require_win=True)
    with pytest.raises(HarborError, match="victory not earned"):
        export_bundle(world(), demo_actions()[:-2], require_win=True)


@pytest.mark.parametrize("mutation", [
    lambda b: b["events"][0]["action"].update({"direction": "west"}),
    lambda b: b["events"][0].update({"sequence": 99}),
    lambda b: b["events"][1].update({"previous": "0" * 64}),
    lambda b: b["events"][2].update({"after": "f" * 64}),
    lambda b: b["state"].update({"coins": 900}),
    lambda b: b["source"]["resources"][0].update({"quantity": 30}),
    lambda b: b.update({"source_digest": "0" * 64}),
    lambda b: b.update({"terminal_digest": "0" * 64}),
    lambda b: b.update({"bundle_digest": "0" * 64}),
])
def test_tampering_is_rejected_even_when_export_is_well_formed(mutation):
    bundle = won_bundle()
    mutation(bundle)
    with pytest.raises(HarborError):
        verify_bundle(bundle)


def test_attacker_cannot_reseal_modified_actions_with_only_outer_digest():
    bundle = won_bundle()
    bundle["events"][0]["action"]["direction"] = "west"
    bundle["bundle_digest"] = digest({k: v for k, v in bundle.items() if k != "bundle_digest"})
    with pytest.raises(HarborError, match="replay event chain"):
        verify_bundle(bundle)


def test_extra_fields_and_unbounded_events_are_rejected():
    bundle = won_bundle()
    bundle["unexpected"] = True
    with pytest.raises(HarborError, match="bundle fields"):
        verify_bundle(bundle)
    bundle = won_bundle()
    bundle["events"] = bundle["events"] * 20
    bundle["bundle_digest"] = digest({k: v for k, v in bundle.items() if k != "bundle_digest"})
    with pytest.raises(HarborError):
        verify_bundle(bundle)


def test_bad_json_rejected_before_gameplay():
    for raw in (
        b'{"a":1,"a":2}',
        b'{"n":NaN}',
        b'{"n":Infinity}',
        b'{"n":-Infinity}',
        b'\xff',
        b'{"a":',
        b' ' * (MAX_SOURCE_BYTES + 1),
    ):
        with pytest.raises(HarborError):
            decode(raw, MAX_SOURCE_BYTES)


@pytest.mark.parametrize("action", [
    {"op": "move", "direction": "north"},
    {"op": "move", "direction": "northeast"},
    {"op": "craft", "recipe": "lantern"},
    {"op": "gather"},
    {"op": "trade", "item": "food"},
    {"op": "deliver"},
    {"op": "choose", "choice": "signal"},
    {"op": "wait", "unexpected": 1},
    {"op": "move", "direction": "east", "extra": "unsafe"},
    {"op": "execute", "script": "print('unsafe')"},
])
def test_invalid_player_actions_fail_closed_without_state_mutation(action):
    source = world()
    before = initial_state(source)
    original = deepcopy(before)
    with pytest.raises(HarborError):
        step(source, before, action)
    assert before == original


def test_resource_depletion_and_inventory_crafting_are_real():
    source = world()
    actions = demo_actions()[:3]
    state, events = run(source, actions)
    assert state["stock"]["wood"] == 0
    assert state["inventory"]["wood"] == 2
    assert len(events) == 3
    with pytest.raises(HarborError, match="exhausted"):
        step(source, state, {"op": "gather"})
    crafted, _ = run(source, demo_actions()[:12])
    assert crafted["inventory"]["lantern"] == 1
    assert crafted["inventory"]["ration"] == 1
    assert crafted["inventory"].get("wood", 0) == 0


def test_trade_requires_npc_adjacency_and_deducts_finite_stock_and_coins():
    source = world()
    state, _ = run(source, [
        {"op": "move", "direction": "east"},
        {"op": "move", "direction": "east"},
        {"op": "move", "direction": "east"},
        {"op": "move", "direction": "east"},
        {"op": "move", "direction": "south"},
    ])
    assert state["pos"] == [5, 2]
    # NPC patrol is on the same row and cannot occupy the player's tile.
    assert state["npc_pos"] != state["pos"]
    # A deterministic adjacent trader encounter can be constructed from the authored route.
    state["pos"] = [4, 1]
    state["npc_pos"] = [4, 2]
    before = deepcopy(state)
    after = step(source, state, {"op": "trade", "item": "food"})
    assert after["coins"] == before["coins"] - source["npc"]["price"]
    assert after["inventory"]["food"] == 1
    assert after["npc_stock"]["food"] == before["npc_stock"]["food"] - 1
    assert state == before


def test_npc_collision_is_checked_before_movement():
    source = world()
    state = initial_state(source)
    state["pos"] = [4, 1]
    state["npc_pos"] = [4, 2]
    with pytest.raises(HarborError, match="collision"):
        step(source, state, {"op": "move", "direction": "south"})


@pytest.mark.parametrize("change", [
    lambda s: s["map"].__setitem__(0, ".#######"),
    lambda s: s.update({"start": [0, 0]}),
    lambda s: s.update({"dock": [1, 1]}),
    lambda s: s["resources"][0].update({"quantity": True}),
    lambda s: s["resources"][1].update({"id": "wood"}),
    lambda s: s["npc"]["route"].append([1, 1]),
    lambda s: s["npc"].update({"price": 0}),
    lambda s: s["recipes"][0].update({"id": "ration"}),
    lambda s: s.update({"delivery": {"impossible": 1}}),
    lambda s: s.update({"max_ticks": 1000000}),
    lambda s: s.update({"unknown": "extra"}),
])
def test_invalid_authoring_is_rejected(change):
    source = world()
    change(source)
    with pytest.raises(HarborError):
        validate_source(source)


def test_world_is_defensively_copied_before_execution():
    source = world()
    validated = validate_source(source)
    source["map"][1] = "########"
    assert validated["map"][1] != source["map"][1]
    assert won_bundle()["state"]["ending"] == "beacon"


def test_scripted_cli_demo_and_portable_verify_round_trip(tmp_path):
    command = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]
    demo = subprocess.run(command + ["demo", "--require-win"], capture_output=True, check=False)
    assert demo.returncode == 0, demo.stderr.decode()
    bundle = decode(demo.stdout)
    assert bundle["state"]["ending"] == "beacon"
    target = tmp_path / "save.json"
    target.write_bytes(demo.stdout)
    verified = subprocess.run(command + ["verify", "--bundle", str(target), "--require-win"], capture_output=True, check=False)
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["state"] == bundle["state"]


def test_cli_accepts_player_authored_actions_and_rejects_illegal_input(tmp_path):
    command = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]
    actions = tmp_path / "actions.json"
    actions.write_bytes(canonical(demo_actions()))
    success = subprocess.run(command + ["play", "--actions", str(actions), "--require-win"], capture_output=True, check=False)
    assert success.returncode == 0, success.stderr.decode()
    assert decode(success.stdout)["state"]["ending"] == "beacon"
    actions.write_bytes(canonical([{"op": "move", "direction": "north"}]))
    failure = subprocess.run(command + ["play", "--actions", str(actions)], capture_output=True, check=False)
    assert failure.returncode == 2
    assert failure.stdout == b""
    assert b"collision" in failure.stderr


def test_cli_refuses_corrupt_save_and_does_not_claim_success(tmp_path):
    bundle = won_bundle()
    bundle["state"]["ending"] = "forged"
    save = tmp_path / "save.json"
    save.write_bytes(canonical(bundle))
    command = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli", "verify", "--bundle", str(save)]
    failed = subprocess.run(command, capture_output=True, check=False)
    assert failed.returncode == 2
    assert failed.stdout == b""


def test_source_and_bundle_sizes_are_bounded():
    source = world()
    source["map"] = ["#" * 33] * 3
    with pytest.raises(HarborError):
        validate_source(source)
    with pytest.raises(HarborError):
        decode(b" " * (MAX_BUNDLE_BYTES + 1))
    assert len(canonical(won_bundle())) < MAX_BUNDLE_BYTES
