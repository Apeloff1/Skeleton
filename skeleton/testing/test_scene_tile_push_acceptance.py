"""Push-puzzle acceptance proves earned plates, restart and export."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.scene_tile_push import (
    original_push, simulate_push,
)
from skeleton.game.gameplay.scene_tile_push_acceptance import accept_push
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_source_to_terminal_acceptance_requires_real_puzzle_solution():
    source, actions = original_push()
    final = simulate_push(source, actions)
    report = accept_push(source, actions)
    assert report["phase"] == "won"
    assert report["final_state_digest"] == final["state_digest"]
    assert report["verified_restart"] is True
    assert report["verified_editor_preview"] is True
    assert report["verified_export"] is True


def test_partial_push_script_does_not_get_victory_certificate():
    source, actions = original_push()
    with pytest.raises(SceneTravelError):
        accept_push(source, actions[:-1])
