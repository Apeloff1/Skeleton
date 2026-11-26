"""Source-bound catalog audit continuation across CLI and typed Jeeves tools."""
from __future__ import annotations

import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder import studio_ecosystem_walk_coverage_batch as batch
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def test_catalog_continuation_replays_same_authoritative_index():
    first = batch.audit_catalog_walk_choices(authorized=True, offset=0, limit=1)
    assert first["projects_examined"] == 1
    assert first["continuation"]["catalog_digest"] == first["catalog_digest"]
    assert first["continuation"]["offset"] == first["next_offset"]
    second = batch.audit_catalog_walk_choices(
        authorized=True, offset=first["next_offset"], limit=1,
        expected_catalog_digest=first["catalog_digest"],
    )
    assert second["page_offset"] == 1
    assert second["catalog_digest"] == first["catalog_digest"]
    assert first["projects"][0]["project_id"] != second["projects"][0]["project_id"]


def test_jeeves_typed_continuation_matches_canonical_page():
    orchestrator = JeevesGameOrchestrator()
    first = orchestrator.authoritative_walk_catalog({
        "schema": tool.CATALOG_REQUEST_SCHEMA, "offset": 0, "limit": 1,
    }, authorized=True)
    second = orchestrator.authoritative_walk_catalog({
        "schema": tool.CATALOG_REQUEST_SCHEMA, "offset": 1, "limit": 1,
        "expected_catalog_digest": first["catalog_digest"],
    }, authorized=True)
    assert second["detail"]["page_offset"] == 1
    assert second["catalog_digest"] == first["catalog_digest"]
    assert second["result_digest"] == orchestrator.authoritative_walk_catalog({
        "schema": tool.CATALOG_REQUEST_SCHEMA, "offset": 1, "limit": 1,
        "expected_catalog_digest": first["catalog_digest"],
    }, authorized=True)["result_digest"]


@pytest.mark.parametrize("offset,digest", [
    (1, None), (1, "0" * 64), (1, "F" * 64), (1, "g" * 64),
    (1, ""), (0, 123), (0, True),
])
def test_continuation_rejected_before_project_source_read(offset, digest, monkeypatch):
    monkeypatch.setattr(batch, "read_blueprint",
                        lambda *_: pytest.fail("untrusted continuation reached project source"))
    with pytest.raises(StudioQuestError):
        batch.audit_catalog_walk_choices(
            authorized=True, offset=offset, limit=1,
            expected_catalog_digest=digest,
        )


@pytest.mark.parametrize("extra", [
    {"offset": 1}, {"expected_catalog_digest": "F" * 64},
    {"expected_catalog_digest": "g" * 64}, {"expected_catalog_digest": 1},
])
def test_jeeves_rejects_untrusted_continuation_before_catalog(extra, monkeypatch):
    monkeypatch.setattr(batch, "audit_catalog_walk_choices",
                        lambda **_: pytest.fail("invalid request reached catalog"))
    request = {"schema": tool.CATALOG_REQUEST_SCHEMA, "offset": 0, "limit": 1}
    request.update(extra)
    with pytest.raises(StudioQuestError):
        tool.execute_catalog_audit_tool(request, authorized=True)


def test_schema_exposes_digest_without_caller_authorization():
    parameters = tool.catalog_tool_schema()["parameters"]
    assert parameters["properties"]["expected_catalog_digest"]["pattern"] == "^[0-9a-f]{64}$"
    assert "authorized" not in parameters["properties"]
