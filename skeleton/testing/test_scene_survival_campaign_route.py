"""Survival campaign proof cannot be separated from its replayed source."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.scene_survival_campaign import (
    original_campaign, simulate_campaign,
)
from skeleton.game.gameplay.scene_survival_campaign_route import (
    solve_campaign, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_route_matches_earned_terminal_state_and_portable_identity():
    source, _ = original_campaign()
    proof = solve_campaign(source, max_states=1024, max_depth=32)
    final = verify_plan(proof, source=source)
    assert proof["status"] == "found"
    assert final == simulate_campaign(source, proof["actions"])
    assert final["state_digest"] == proof["final_state_digest"]


def test_modified_portable_receipt_is_not_valid_witness():
    source, _ = original_campaign()
    proof = solve_campaign(source, max_states=1024, max_depth=32)
    forged = copy.deepcopy(proof)
    forged["portable_checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        verify_plan(forged, source=source)
