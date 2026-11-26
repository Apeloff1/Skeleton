"""Jeeves character experience is read-only, authorized and source-leased."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program,
)
from skeleton.ai.game_builder.studio_quest_character_jeeves import (
    register_quest_character_experience_tools,
)
from tests.test_studio_quest_character_experience import fixture


def test_jeeves_character_assembly_authority_and_handoff():
    parts = fixture()
    registry = CapabilityRegistry()
    register_quest_character_experience_tools(registry, *parts)
    request = {"expected_source_digest": compile_quest_program(parts[0]).source_digest}
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_character_compile", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_character_compile", request,
                            authorized=True)["executed"] is False
    receipt = registry.execute("studio_quest_character_compile", request,
                               authorized=True, dry_run=False)
    handoff = registry.execute("studio_quest_character_handoff", request,
                               authorized=True, dry_run=False)
    assert receipt["character_experience_digest"] == handoff["character_experience_digest"]
    assert handoff["release_certified"] is False


def test_jeeves_character_rejects_stale_source_and_input_mutation():
    parts = fixture()
    registry = CapabilityRegistry()
    register_quest_character_experience_tools(registry, *parts)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_character_compile", {
            "expected_source_digest": "0" * 64,
        }, authorized=True, dry_run=False)
    parts[2]["final_trust"][0]["trust"] = 99
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_character_compile", {
            "expected_source_digest": compile_quest_program(parts[0]).source_digest,
        }, authorized=True, dry_run=False)
