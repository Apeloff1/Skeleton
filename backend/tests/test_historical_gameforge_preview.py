"""Preview API compatibility for recovered seven-stage archive #807."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.routes.skeleton_gameforge import (
    HistoricalConductorPreviewRequest,
    historical_conductor_preview,
)


@pytest.mark.parametrize("genre", [
    "platformer", "puzzle", "rpg", "shooter", "strategy",
    "racing", "adventure", "sandbox",
])
def test_historical_genres_produce_bounded_manifest_without_file_write(genre):
    req = HistoricalConductorPreviewRequest(
        title="Old School " + genre,
        pitch="A playable original proof of concept",
        genre=genre,
        pillars=["navigation", "challenge"],
    )
    out = historical_conductor_preview(req)
    assert out["ok"] is True
    assert out["mode"] == "historical_7_stage_preview"
    assert len(out["completed"]) == 7
    assert out["artifact_count"] > 0
    assert out["byte_total"] <= 1_000_000
    assert out["manifest"]


@pytest.mark.parametrize("override", [
    {"genre": "unknown-game"},
    {"era": "UNKNOWN_ERA"},
    {"target": "unsafe"},
    {"pillars": []},
])
def test_invalid_creator_steering_rejected(override):
    params = {"title": "Old School", "pitch": "Original game", "genre": "platformer"}
    req = HistoricalConductorPreviewRequest(**{**params, **override})
    with pytest.raises(HTTPException) as exc:
        historical_conductor_preview(req)
    assert exc.value.status_code == 422
