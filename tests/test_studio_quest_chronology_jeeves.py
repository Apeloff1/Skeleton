"""Jeeves chronology tools reject unauthorized or stale authored time."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_chronology import PROMPT
from skeleton.ai.game_builder.studio_quest_chronology_jeeves import (
    register_quest_chronology_tools,
)
from tests.test_studio_quest_character_locale import fixture


def test_jeeves_chronology_proposal_compile_and_authority():
    documents = fixture()[0]
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    registry = CapabilityRegistry()
    register_quest_chronology_tools(registry, documents)
    request = {
        "prompt": PROMPT,
        "actions": [[stage.key, stage.alternatives[0]] for stage in program.stages],
        "expected_source_digest": program.source_digest,
        "expected_initial_session_digest": initial.digest,
    }
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_chronology_proposal", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_chronology_proposal", request,
                            authorized=True)["executed"] is False
    plan = registry.execute("studio_quest_chronology_proposal", request,
                            authorized=True, dry_run=False)
    for row in plan["rows"]:
        row["reviewed"] = True
    result = registry.execute("studio_quest_chronology_compile", {
        "plan": plan,
        "expected_source_digest": program.source_digest,
        "expected_initial_session_digest": initial.digest,
    }, authorized=True, dry_run=False)
    assert result["temporal_window_consistency_verified"] is True
    assert result["native_gameplay_verified"] is False


def test_jeeves_chronology_rejects_stale_source():
    documents = fixture()[0]
    registry = CapabilityRegistry()
    register_quest_chronology_tools(registry, documents)
    documents["quest"]["stage_graph"][0]["reward"] = "forged"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_chronology_proposal", {
            "prompt": PROMPT, "actions": [],
            "expected_source_digest": "0" * 64,
            "expected_initial_session_digest": "0" * 64,
        }, authorized=True, dry_run=False)
