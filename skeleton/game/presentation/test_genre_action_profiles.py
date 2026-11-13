"""Full canonical multi-genre control and safety contracts."""
from __future__ import annotations

import pytest

from skeleton.context.questionnaire import BRIEF_ERA_VOTES
from skeleton.game.presentation.genre_action_profiles import (
    FAMILIES, GENRE_FAMILY, genre_action_map, genre_control_profile,
)
from skeleton.game.presentation.input_actions import (
    ActionMap, Control, InputContractError, InputState,
)


def test_every_canonical_questionnaire_genre_has_a_control_scheme():
    all_genres = set(BRIEF_ERA_VOTES["genre"])
    assert all_genres <= set(GENRE_FAMILY)
    assert set(GENRE_FAMILY.values()) == FAMILIES
    for genre in sorted(all_genres):
        profile = genre_control_profile(genre)
        assert profile["family"] in FAMILIES
        assert len(profile["actions"]) >= 3
        assert any(b["control"].startswith("keyboard:") for b in profile["bindings"])
        assert any(b["control"].startswith("gamepad:") for b in profile["bindings"])


def test_all_eight_archived_conductor_genres_have_maps():
    for genre in ("platformer", "puzzle", "rpg", "shooter", "strategy", "racing", "adventure", "sandbox"):
        p = genre_control_profile(genre)
        assert p["genre"] == genre


def test_rpg_keyboard_gamepad_and_touch_remap_to_semantic_attack():
    for device_path in ("mouse:button.left", "gamepad:button.west", "touch:tap"):
        state = InputState(genre_action_map("rpg"))
        state.feed(device_path, 1.0)
        state.update()
        assert state.pressed("attack")
        state.update()
        assert not state.pressed("attack")


def test_racing_steer_is_an_axis_and_a_gameplay_value():
    state = InputState(genre_action_map("racing"))
    state.feed("keyboard:key.a", 1)
    state.update()
    assert state.value("steer") == -1.0


def test_control_remaps_do_not_mutate_other_game_sessions():
    first = genre_action_map("rpg")
    second = genre_action_map("rpg")
    first.rebind("attack", Control.parse("mouse:button.left"), Control.parse("mouse:button.middle"))
    assert first.bindings() != second.bindings()


@pytest.mark.parametrize("genre", ("__proto__", "", "unknown", 1, None))
def test_unknown_genre_rejected(genre):
    with pytest.raises(InputContractError):
        genre_action_map(genre)
