"""Converged B024 input profiles with all 158 creator genres."""
from __future__ import annotations

import pytest
from skeleton.context.genre_catalog import GENRE_COUNT, GENRE_ERA_VOTES
from skeleton.game.presentation.genre_action_profiles import (
    GENRE_FAMILY, GALAXY_GENRE_FAMILY, QUESTIONNAIRE_GENRE_FAMILY,
    genre_action_map, genre_control_profile,
)
from skeleton.game.presentation.genre_playable_adapter import playable_input_profile
from skeleton.game.presentation.input_actions import InputContractError


def test_all_158_creator_labels_have_presentable_semantic_controls():
    assert GENRE_COUNT == 158
    assert set(GENRE_ERA_VOTES) <= set(GENRE_FAMILY)
    assert len(GALAXY_GENRE_FAMILY) == 67
    for genre in sorted(GENRE_ERA_VOTES):
        profile = genre_control_profile(genre)
        assert profile["genre"] == genre
        assert "gameforge-extended" in profile["catalogs"]
        assert profile["actions"]
        assert any(b["control"].startswith("keyboard:") for b in profile["bindings"])
        assert any(b["control"].startswith("gamepad:") for b in profile["bindings"])


def test_historical_control_choices_preserve_explicit_precedence():
    for genre, family in GALAXY_GENRE_FAMILY.items():
        if genre not in QUESTIONNAIRE_GENRE_FAMILY:
            assert GENRE_FAMILY[genre] == family
    for genre, family in QUESTIONNAIRE_GENRE_FAMILY.items():
        assert GENRE_FAMILY[genre] == family


@pytest.mark.parametrize("genre", ["arena-shooter", "tactical-rpg", "farming-sim", "escape-room", "survival-horror", "endless-runner"])
def test_extended_genres_build_fresh_input_maps(genre):
    first, second = genre_action_map(genre), genre_action_map(genre)
    assert first is not second
    assert first.bindings() == second.bindings()


def test_analog_only_racing_is_not_falsely_grid_playable():
    with pytest.raises(InputContractError):
        playable_input_profile("racing")


def test_invalid_genre_never_becomes_valid_from_extended_catalog():
    with pytest.raises(InputContractError):
        genre_control_profile("../../private")
