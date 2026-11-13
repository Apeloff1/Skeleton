"""End-to-end evacuation acceptance requires earned rescue and replay proof."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.scene_evacuation import (
    demo_actions, original_evacuation, simulate_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_acceptance import accept_evacuation
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_every_restart_boundary_and_portable_witness_are_earned():
    source, actions = original_evacuation(), demo_actions()
    saved = simulate_evacuation(source, actions)
    receipt = accept_evacuation(source, actions)
    assert receipt["phase"] == "evacuated"
    assert receipt["source_digest"] == saved["source_digest"]
    assert receipt["state_digest"] == saved["state_digest"]
    assert receipt["checkpoints_verified"] == len(actions) + 1
    assert receipt["reward"] == saved["state"]["reward"]


def test_missing_final_turn_cannot_claim_acceptance():
    source, actions = original_evacuation(), demo_actions()
    with pytest.raises(SceneTravelError):
        accept_evacuation(source, actions[:-1])
