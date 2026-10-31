"""Jeeves catalog merge delegates to the authoritative replay engine."""
from __future__ import annotations

import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def test_jeeves_merge_roundtrip_is_source_bound():
    page = batch.audit_catalog_walk_choices(authorized=True, limit=1)
    request = {"schema": tool.CATALOG_MERGE_REQUEST_SCHEMA, "pages": [page]}
    result = JeevesGameOrchestrator().authoritative_walk_catalog_merge(
        request, authorized=True,
    )
    assert result["schema"] == tool.CATALOG_MERGE_RESULT_SCHEMA
    assert result["detail"]["pages_verified"] == 1
    assert result["catalog_digest"] == page["catalog_digest"]
    assert result["result_digest"] == tool.execute_catalog_merge_tool(
        request, authorized=True,
    )["result_digest"]
    assert result["release_certified"] is False


@pytest.mark.parametrize("request", [
    {}, {"schema": "bad", "pages": [{}]},
    {"schema": tool.CATALOG_MERGE_REQUEST_SCHEMA, "pages": []},
    {"schema": tool.CATALOG_MERGE_REQUEST_SCHEMA, "pages": [{}] * 5},
    {"schema": tool.CATALOG_MERGE_REQUEST_SCHEMA, "pages": [{}], "authorized": True},
])
def test_invalid_jeeves_merge_request_fails_before_catalog(request, monkeypatch):
    monkeypatch.setattr(batch, "merge_catalog_walk_audits",
                        lambda *_a, **_k: pytest.fail("untrusted request reached source"))
    with pytest.raises(StudioQuestError):
        tool.execute_catalog_merge_tool(request, authorized=True)


def test_jeeves_merge_denies_unauthorized_before_any_source(monkeypatch):
    monkeypatch.setattr(batch, "merge_catalog_walk_audits",
                        lambda *_a, **_k: pytest.fail("unauthorized source read"))
    with pytest.raises(PermissionError):
        tool.execute_catalog_merge_tool({
            "schema": tool.CATALOG_MERGE_REQUEST_SCHEMA, "pages": [{}],
        }, authorized=False)
