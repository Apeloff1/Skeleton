"""Cross-feature source contracts for original creator and native quest integration.

No network, model provider, device GPS, disk publication or external Godot needed.
"""
from __future__ import annotations

import pytest

from backend.routes.skeleton_gameforge import RunRequest
from skeleton.context.pipeline import apply_operator_axes, normalise_operator_axes
from skeleton.context.tensor import ContextTensor
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.ai.game_builder.godot_quest_bridge import (
    QUEST_PATH,
    attach_native_quest,
    verify_native_quest,
)


def test_api_accepts_safe_genre_design_axes_and_native_quest_in_one_input():
    request = RunRequest(
        vision="A coastal colony with authored room objectives",
        answers={"genre": "colony-sim"},
        operator_axes={"risk": 0.81, "tempo": 0.23},
        quest_content=True,
        quest_length=6,
        target="godot",
    )
    assert request.answers["genre"] == "colony-sim"
    assert request.quest_content and request.quest_length == 6
    assert normalise_operator_axes(request.operator_axes) == {
        "risk": 0.81, "tempo": 0.23
    }
    tensor = apply_operator_axes(
        ContextTensor.from_era("extraction_now"), request.operator_axes
    )
    assert tensor["risk"] == 0.81
    assert tensor["tempo"] == 0.23
    files, receipt = attach_native_quest(
        emit_godot(compile_era("extraction_now")), length=request.quest_length
    )
    assert receipt["steps"] == 6
    assert receipt["replay_verified"] is True
    assert QUEST_PATH in files
    assert verify_native_quest(files)


@pytest.mark.parametrize("value", [0, 9, -1])
def test_quest_length_bounds_enforced_at_api_boundary(value):
    with pytest.raises(Exception):
        RunRequest(quest_content=True, quest_length=value)


def test_unsafe_operator_axes_fail_closed_even_with_native_quest_enabled():
    req = RunRequest(
        answers={"genre": "colony-sim"},
        operator_axes={"risk": float("nan")},
        quest_content=True,
    )
    with pytest.raises(ValueError):
        normalise_operator_axes(req.operator_axes)
