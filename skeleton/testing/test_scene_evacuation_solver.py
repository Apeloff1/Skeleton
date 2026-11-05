"""Evacuation route hints remain canonical replay witnesses, not authority."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.scene_evacuation import (
    demo_actions, original_evacuation, simulate_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_solver import solve_evacuation
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_authored_hint_only_becomes_proof_after_full_replay():
    source, actions = original_evacuation(), demo_actions()
    receipt = solve_evacuation(source, hint_actions=actions)
    earned = simulate_evacuation(source, actions)
    assert receipt["status"] == "found"
    assert receipt["actions"] == actions
    assert receipt["source_digest"] == earned["source_digest"]
    assert receipt["state_digest"] == earned["state_digest"]
    assert receipt["reward"] == earned["state"]["reward"]


@pytest.mark.parametrize("nodes,depth", [(0, 4), (4097, 4),
                                       (True, 4), (8, 0), (8, 33)])
def test_solver_rejects_invalid_resource_budgets(nodes, depth):
    with pytest.raises(SceneTravelError):
        solve_evacuation(original_evacuation(), max_nodes=nodes,
                         max_depth=depth)
