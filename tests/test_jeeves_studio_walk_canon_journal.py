"""Typed Jeeves canon journal uses the canonical source-bound runtime."""
import pytest

from skeleton.ai.agents.jeeves import studio_walk_tool as tool
from skeleton.ai.agents.jeeves.jeeves_game_orchestrator import JeevesGameOrchestrator
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

PROJECT = "studio_arena_fighting_glacial_fjord"


def request(**kwargs):
    data = {"schema": tool.REQUEST_SCHEMA, "project_id": PROJECT,
            "operation": "journal", "events": []}
    data.update(kwargs)
    return data


def test_journal_is_real_offline_and_deterministic():
    jeeves = JeevesGameOrchestrator()
    result = jeeves.authoritative_walk(request(), authorized=True)
    assert result == jeeves.authoritative_walk(request(), authorized=True)
    assert result["detail"]["schema"] == "skeleton.game_builder.studio_walk_canon_journal.v1"
    assert result["detail"]["next_authored_scene"]["index"] == 0
    assert result["detail"]["session_digest"] == result["receipt"]["session_digest"]
    assert result["detail"]["release_certified"] is False


def test_journal_denies_forged_and_misrouted_tool_arguments():
    jeeves = JeevesGameOrchestrator()
    with pytest.raises(PermissionError):
        jeeves.authoritative_walk(request(), authorized=False)
    for kwargs in (
        {"journal_limit": True}, {"journal_limit": 9},
        {"journal_offset": -1}, {"journal_offset": 1},
        {"journal_expected_session_digest": "0" * 64},
        {"journal_expected_source_digest": "0" * 64},
        {"operation": "route", "journal_limit": 2},
        {"authorized": True},
    ):
        with pytest.raises(StudioQuestError):
            jeeves.authoritative_walk(request(**kwargs), authorized=True)
