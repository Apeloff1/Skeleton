"""Push solver returns only canonical replayed, bounded game witnesses."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.scene_tile_push import (
    new_push, original_push, resume_push,
)
from skeleton.game.gameplay.scene_tile_push_solver import solve_push
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_shortest_route_replays_through_authoritative_push_reducer():
    source, _ = original_push()
    proof = solve_push(source, max_states=512, max_depth=24)
    assert proof["status"] == "found"
    saved = resume_push(new_push(source), proof["actions"])
    assert saved["state"]["phase"] == "won"
    assert saved["state_digest"] == proof["final_state_digest"]


def test_resource_exhaustion_is_inconclusive_not_unreachable():
    source, _ = original_push()
    proof = solve_push(source, max_states=1, max_depth=1)
    assert proof["status"] == "inconclusive"
    assert proof["budget_exhausted"] is True
    assert proof["final_state_digest"] is None
    with pytest.raises(SceneTravelError):
        solve_push(source, max_states=0)
