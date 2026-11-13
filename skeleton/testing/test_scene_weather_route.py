"""Weather route replay, source identity and bounded-search semantics."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.scene_weather import original_weather, simulate_weather
from skeleton.game.gameplay.scene_weather_route import (
    solve_weather_route, verify_weather_route,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_completed_checkpoint_witness_has_exact_zero_action_replay():
    source, actions = original_weather()
    completed = simulate_weather(source, actions)
    proof = solve_weather_route(session=completed,
                                max_states=1, max_depth=1)
    assert proof["status"] == "proven_win"
    assert proof["actions"] == []
    assert verify_weather_route(proof, session=completed) == completed


def test_witness_cannot_be_forged_by_editing_state_digest():
    source, actions = original_weather()
    completed = simulate_weather(source, actions)
    proof = solve_weather_route(session=completed,
                                max_states=1, max_depth=1)
    forged = copy.deepcopy(proof)
    forged["final_state_digest"] = "0" * 64
    with pytest.raises(SceneTravelError):
        verify_weather_route(forged, session=completed)
