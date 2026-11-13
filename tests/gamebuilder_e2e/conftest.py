"""Shared fixtures for the AI game builder end-to-end suite.

Every test drives the real ``skeleton.forge.game_builder.build_playable_game``
executor with the Godot playtest off, so no engine binary or network is needed.
Builds are cached per (brief, era, archetype) to keep the suite fast.
"""
from __future__ import annotations

import functools
from typing import Any

import pytest

from skeleton.forge.game_builder import build_playable_game
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS

GENRES = tuple(item["genre"] for item in GOLDEN_BRIEFS)
ERAS = (
    "arcade_golden_age", "boomer_shooter", "cozy_wholesome", "extraction_now",
    "horror_survival", "indie_experimental", "modern_aaa", "soulslike",
)


@functools.lru_cache(maxsize=64)
def _cached(brief: str, era: str | None, archetype: str) -> dict[str, Any]:
    return build_playable_game(brief, era=era, archetype=archetype, playtest_mode="off", deadline_s=90)


def build(brief: str, *, era: str | None = None, archetype: str = "auto") -> dict[str, Any]:
    return _cached(brief, era, archetype)


def golden(genre: str) -> str:
    return next(item["brief"] for item in GOLDEN_BRIEFS if item["genre"] == genre)


@pytest.fixture(params=GENRES)
def genre(request) -> str:
    return request.param
