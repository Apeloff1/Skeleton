"""Design spec compiled from the brief."""
from __future__ import annotations

import re

import pytest

from tests.gamebuilder_e2e.conftest import build, golden


def test_spec_genre_matches_golden(genre):
    assert build(golden(genre))["spec"]["genre"] == genre


def test_spec_shape(genre):
    spec = build(golden(genre))["spec"]
    assert spec["schema_version"] == "skeleton.game_design_spec.v1"
    assert spec["engine"] == "godot4"
    assert spec["scope"] == "small"
    assert re.fullmatch(r"[0-9a-f]{64}", spec["spec_id"])
    assert spec["title"].strip()
    assert spec["core_loop"].strip()
    assert isinstance(spec["systems"], list) and spec["systems"]


def test_spec_is_deterministic(genre):
    from skeleton.forge.game_builder import build_playable_game

    again = build_playable_game(golden(genre), playtest_mode="off", deadline_s=90)
    assert again["spec"]["spec_id"] == build(golden(genre))["spec"]["spec_id"]


@pytest.mark.parametrize(
    "brief,expected",
    [
        ("a twin-stick bullet horde game", "top_down_shooter"),
        ("a side-scroll jump game", "platformer"),
        ("a permadeath dungeon crawler", "rpg_roguelike"),
        ("a small platformer about a fox", "platformer"),
        ("a quest through ruined towers", "rpg_roguelike"),
    ],
)
def test_genre_keywords(brief, expected):
    assert build(brief)["spec"]["genre"] == expected


def test_content_matches_spec(genre):
    result = build(golden(genre))
    content = result["content"]
    assert content["schema_version"] == result["content_schema"]
    assert content["genre"] == genre
    assert content["spec_id"] == result["spec"]["spec_id"]
