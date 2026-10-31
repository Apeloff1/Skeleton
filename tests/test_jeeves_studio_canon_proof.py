"""Typed Jeeves canon proof has real original source and strict authority."""
import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"


def request(**changes):
    body = {"schema": tool.CANON_PROOF_REQUEST_SCHEMA, "project_id": PROJECT}
    body.update(changes)
    return body


def test_jeeves_canon_proof_is_source_bound_and_deterministic():
    jeeves = JeevesGameOrchestrator()
    first = jeeves.authoritative_canon_proof(request(), authorized=True)
    assert first == jeeves.authoritative_canon_proof(request(), authorized=True)
    assert first["detail"]["checked_scene_count"] == 3
    assert first["detail"]["release_certified"] is False
    assert first["schema"] == tool.CANON_PROOF_RESULT_SCHEMA


def test_jeeves_canon_proof_rejects_forged_authority_and_unknown_fields():
    jeeves = JeevesGameOrchestrator()
    with pytest.raises(PermissionError):
        jeeves.authoritative_canon_proof(request(), authorized=False)
    with pytest.raises(StudioQuestError):
        jeeves.authoritative_canon_proof(request(admin=True), authorized=True)
    with pytest.raises(StudioQuestError):
        jeeves.authoritative_canon_proof(request(schema="unsupported"), authorized=True)
