"""All published evacuation choices are replay-legal at every checkpoint."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.scene_evacuation import (
    _advance, demo_actions, original_evacuation, simulate_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_board import (
    inspect_evacuation, legal_evacuation_actions,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_boards_follow_every_authored_action_without_mutation():
    source, actions = original_evacuation(), demo_actions()
    for cut in range(len(actions) + 1):
        session = simulate_evacuation(source, actions[:cut])
        unchanged = copy.deepcopy(session)
        board = inspect_evacuation(session)
        assert board["state_digest"] == session["state_digest"]
        assert board["source_digest"] == session["source_digest"]
        assert board["legal_actions"] == legal_evacuation_actions(session)
        for action in board["legal_actions"]:
            assert _advance(session, action)["state"]["tick"] == cut + 1
        if session["state"]["phase"] != "active":
            assert board["legal_actions"] == []
        assert session == unchanged


def test_forged_checkpoint_cannot_publish_choices():
    source = original_evacuation()
    session = simulate_evacuation(source, [])
    session["state"]["supplies"] += 1
    with pytest.raises(SceneTravelError):
        inspect_evacuation(session)
