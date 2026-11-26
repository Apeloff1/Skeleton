"""Recovered historical planner is bounded and remains a source-only preview."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.routes.skeleton_gameforge import (
    HistoricalConductorPreviewRequest,
    historical_conductor_preview,
)


def _request(**overrides):
    return HistoricalConductorPreviewRequest(
        **{"title": "Original ridge", "pitch": "Explore a ridge and solve a puzzle",
           "genre": "puzzle", "pillars": ["exploration", "puzzles"], **overrides}
    )


def test_real_seven_stage_preview_returns_receipts_not_source_bytes():
    response = historical_conductor_preview(_request())
    assert response["ok"] is True
    assert response["mode"] == "historical_7_stage_preview"
    assert len(response["completed"]) == 7
    assert response["artifact_count"] == len(response["artifacts"])
    assert 0 < response["byte_total"] <= 1_000_000
    assert all(isinstance(name, str) for name in response["artifacts"])
    assert isinstance(response["manifest"], dict)


@pytest.mark.parametrize("overrides", [
    {"genre": "unsupported-private-genre"},
    {"era": "unknown-era"},
    {"target": "untrusted-target"},
    {"pillars": ["x" * 101]},
])
def test_preview_rejects_unsupported_inputs(overrides):
    with pytest.raises(HTTPException) as caught:
        historical_conductor_preview(_request(**overrides))
    assert caught.value.status_code == 422


@pytest.mark.parametrize("overrides", [
    {"budget_bytes": 1_000_001}, {"regions": 21},
    {"pillars": []}, {"pillars": ["x"] * 6},
])
def test_preview_rejects_out_of_budget_request(overrides):
    with pytest.raises(ValidationError):
        _request(**overrides)
