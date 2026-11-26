"""Typed Jeeves catalog audit uses the same bounded canonical CLI authority."""
from __future__ import annotations

import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def request(**updates):
    body = {
        "schema": tool.CATALOG_REQUEST_SCHEMA, "offset": 0, "limit": 1,
    }
    body.update(updates)
    return body


def test_jeeves_catalog_audit_is_real_and_deterministic():
    orchestrator = JeevesGameOrchestrator()
    result = orchestrator.authoritative_walk_catalog(request(), authorized=True)
    assert result == orchestrator.authoritative_walk_catalog(request(), authorized=True)
    assert result["schema"] == tool.CATALOG_RESULT_SCHEMA
    assert result["detail"]["projects_examined"] == 1
    assert result["catalog_digest"] == result["detail"]["catalog_digest"]
    assert result["detail"]["release_certified"] is False
    assert result["release_certified"] is False
    assert result["result_digest"] and len(result["result_digest"]) == 64


def test_catalog_audit_requires_operator_authority_before_catalog(monkeypatch):
    from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch
    monkeypatch.setattr(batch, "list_blueprints",
                        lambda **_: pytest.fail("unauthorized catalog read"))
    with pytest.raises(PermissionError):
        tool.execute_catalog_audit_tool(request(), authorized=False)


@pytest.mark.parametrize("change", [
    {"schema": "future"}, {"offset": -1}, {"offset": True},
    {"limit": 0}, {"limit": 5}, {"limit": False},
    {"genre": ""}, {"biome": []}, {"authorization": True},
])
def test_invalid_catalog_tool_requests_rejected_before_io(change, monkeypatch):
    from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch
    monkeypatch.setattr(batch, "list_blueprints",
                        lambda **_: pytest.fail("invalid request reached catalog"))
    with pytest.raises(StudioQuestError):
        tool.execute_catalog_audit_tool(request(**change), authorized=True)


def test_catalog_tool_schema_exposes_bounded_no_authority_arguments():
    schema = tool.catalog_tool_schema()
    assert schema["parameters"]["additionalProperties"] is False
    assert schema["parameters"]["required"] == ["schema", "offset", "limit"]
    assert "authorized" not in schema["parameters"]["properties"]
