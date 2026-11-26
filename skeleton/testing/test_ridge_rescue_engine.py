"""Deterministic gameplay, movement, finite crafting, rescue and consequence tests."""
from copy import deepcopy
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.engine import apply, initial_state, replay, available_actions, RescueError

WORLD = parse_world((Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge.json").read_bytes())

def test_initial_state_has_unique_finite_resources():
    state = initial_state(WORLD)
    assert state["turn"] == 0
    assert state["position"] == [0, 0]
    assert state["resources"] == {"pine": 4, "sage": 4, "seam": 4}
    assert state["status"] == "playing"

def test_movement_collision_and_no_mutation_on_invalid_action():
    state = initial_state(WORLD)
    old = deepcopy(state)
    with pytest.raises(RescueError):
        apply(WORLD, state, {"verb": "move", "direction": "west"})
    assert state == old
    moved = apply(WORLD, state, {"verb": "move", "direction": "east"})
    assert moved["position"] == [1, 0]
    assert state == old

def test_source_bound_gather_and_finite_depletion():
    state = initial_state(WORLD)
    state = apply(WORLD, state, {"verb": "move", "direction": "east"})
    for _ in range(4):
        state = apply(WORLD, state, {"verb": "gather", "target": "pine"})
    assert state["inventory"]["wood"] == 4
    assert state["resources"]["pine"] == 0
    with pytest.raises(RescueError):
        apply(WORLD, state, {"verb": "gather", "target": "pine"})

def test_rescue_requires_adjacent_player():
    state = initial_state(WORLD)
    with pytest.raises(RescueError):
        apply(WORLD, state, {"verb": "rescue", "target": "mira"})
    state = apply(WORLD, state, {"verb": "move", "direction": "east"})
    state = apply(WORLD, state, {"verb": "rescue", "target": "mira"})
    assert state["civilians"]["mira"] == "rescued"

def test_crafting_consumes_exact_ingredients():
    state = initial_state(WORLD)
    state["inventory"]["wood"] = 2
    state["inventory"]["ore"] = 1
    made = apply(WORLD, state, {"verb": "craft", "item": "torch"})
    assert made["inventory"]["torch"] == 1
    assert made["inventory"]["wood"] == 0
    assert made["inventory"]["ore"] == 0
    assert state["inventory"]["torch"] == 0
    with pytest.raises(RescueError):
        apply(WORLD, made, {"verb": "craft", "item": "torch"})

def test_earned_endings_and_terminal_rejection():
    state = initial_state(WORLD)
    state["position"] = list(WORLD.shelter)
    state["civilians"] = {key: "rescued" for key in state["civilians"]}
    assert {"verb": "evacuate", "choice": "salvage"} in available_actions(WORLD, state)
    assert {"verb": "evacuate", "choice": "protect"} not in available_actions(WORLD, state)
    won = apply(WORLD, state, {"verb": "evacuate", "choice": "salvage"})
    assert won["status"] == "won:salvage"
    with pytest.raises(RescueError):
        apply(WORLD, won, {"verb": "rest"})
    state["flags"]["beacon"] = True
    protected = apply(WORLD, state, {"verb": "evacuate", "choice": "protect"})
    assert protected["status"] == "won:protect"

def test_replay_is_identical_and_action_history_is_bounded():
    actions = [{"verb": "rest"}, {"verb": "move", "direction": "east"}]
    result = replay(WORLD, actions)
    assert result == apply(WORLD, apply(WORLD, initial_state(WORLD), actions[0]), actions[1])
    with pytest.raises(RescueError):
        replay(WORLD, [{"verb": "rest"}] * 300)
    with pytest.raises(RescueError):
        replay(WORLD, "rest")

def test_storm_and_enemy_are_deterministic():
    a = initial_state(WORLD)
    for _ in range(5):
        a = apply(WORLD, a, {"verb": "rest"})
    b = replay(WORLD, [{"verb": "rest"}] * 5)
    assert a == b
    assert "storm:damage" in a["events"]
