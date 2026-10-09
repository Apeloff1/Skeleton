"""Actual controller-movement validation, not just connected tilemaps."""
from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.ai.runtime.game_playability import (
    MAX_SEARCH_FRAMES, MAX_STATES, check_game_playability,
)
from skeleton.ai.runtime.gameplay_capabilities import (
    GameplayError, compile_level, platformer_replay,
)
from skeleton.ai.runtime.deterministic_capabilities import (
    execute_capability_task,
)

MAP = [
    "########",
    "#S.....#",
    "#...#..#",
    "#......#",
    "#......#",
    "#......#",
    "#......#",
    "#.....G#",
    "########",
]


def test_controller_search_finds_real_winning_game_and_matches_replay():
    outcome = check_game_playability({"tiles": MAP, "max_frames": 96})
    assert outcome["status"] == "playable"
    assert outcome["playable_under_integer_platformer_rules"] is True
    assert 1 <= outcome["controller_frames"] <= 96
    assert outcome["controller_frames"] == len(outcome["controller_actions"])
    replay = platformer_replay({
        "tiles": MAP,
        "avatar": {"x": 1, "y": 1, "vx": 0, "vy": 0},
        "controls": outcome["controller_actions"],
    })
    assert replay["goal_first_reached_frame"] == outcome["controller_frames"]
    assert outcome["model_inference_used"] is False
    assert outcome["training_examples_added"] == 0
    assert outcome["console_hardware_validated"] is False
    assert check_game_playability({"tiles": MAP, "max_frames": 96}) == outcome


def test_real_playability_is_independent_of_abstract_grid_reachability():
    # The goal may be topologically connected, but not reachable by the
    # specific primitive within one horizontal step.
    assert compile_level({"tiles": MAP})["goal_reachable"] is True
    limited = check_game_playability({"tiles": MAP, "max_frames": 1})
    assert limited["playable_under_integer_platformer_rules"] is False
    assert limited["controller_actions"] == []
    assert limited["status"] in (
        "inconclusive_frame_budget", "unreachable_under_current_rules",
    )


@pytest.mark.parametrize("budget", [-1, 0, 97, True, 1.1, "64"])
def test_unbounded_or_malformed_gameplay_search_is_rejected(budget):
    with pytest.raises(GameplayError):
        check_game_playability({"tiles": MAP, "max_frames": budget})


def test_search_refuses_arbitrary_codes_or_untrusted_callbacks():
    with pytest.raises(GameplayError):
        check_game_playability({
            "tiles": MAP, "max_frames": 32, "callback": "__import__('os')",
        })


def test_gameplay_search_exposed_in_pure_typed_operation_catalog():
    receipt = execute_capability_task({
        "operation": "game.playability_check",
        "args": {"tiles": MAP, "max_frames": 96},
    })
    assert receipt["operation"] == "game.playability_check"
    assert receipt["result"]["status"] == "playable"
    assert receipt["model_inference_used"] is False
    assert len(receipt["result_sha256"]) == 64


def test_transient_frame_limit_never_claims_game_is_logically_impossible():
    source = check_game_playability({"tiles": MAP, "max_frames": 1})
    assert source["status"] != "playable"
    assert source["status"] != "game_impossible"
    assert source["search_frame_limit"] == 1
    assert source["console_hardware_validated"] is False


def test_solver_has_explicit_platform_independent_resource_caps():
    assert MAX_SEARCH_FRAMES == 96
    assert MAX_STATES == 12000
    result = check_game_playability({"tiles": MAP, "max_frames": 96})
    assert result["states_explored"] <= MAX_STATES
    assert result["transitions_evaluated"] <= MAX_STATES * 6
    assert len(json.dumps(result)) < 32768
