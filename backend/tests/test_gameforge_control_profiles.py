"""Live app route contracts for recovered B023/B024 controls."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.routes.skeleton_gameforge import (
    gameforge_control_genre, gameforge_control_genres,
)


def test_input_catalog_covers_all_known_creator_genres():
    from skeleton.context.questionnaire import BRIEF_ERA_VOTES
    catalog = gameforge_control_genres()
    assert catalog["count"] >= len(BRIEF_ERA_VOTES["genre"])
    assert set(BRIEF_ERA_VOTES["genre"]) <= set(catalog["genres"])
    assert len(catalog["families"]) == 8


def test_profiles_are_presentable_in_questionnaire_without_device_io():
    p = gameforge_control_genre("shooter")
    assert p["genre"] == "shooter"
    assert p["family"] == "shooter"
    assert any(a["id"] == "aim" for a in p["actions"])
    assert any(b["control"].startswith("touch:") for b in p["bindings"])


def test_invalid_profile_cannot_crash_or_leak_server_state():
    with pytest.raises(HTTPException) as raised:
        gameforge_control_genre("../../../secrets")
    assert raised.value.status_code == 404
