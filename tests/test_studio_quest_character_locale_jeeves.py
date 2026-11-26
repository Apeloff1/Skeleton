"""Jeeves locale handoff is authorized, read-only and exact-source."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program,
)
from skeleton.ai.game_builder.studio_quest_character_locale_jeeves import (
    register_quest_character_locale_tool,
)
from tests.test_studio_quest_character_locale import fixture


def test_jeeves_localized_character_requires_authority():
    parts = fixture()
    registry = CapabilityRegistry()
    register_quest_character_locale_tool(registry, *parts)
    request = {"expected_source_digest": compile_quest_program(parts[0]).source_digest,
               "expected_locale": "en-US"}
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_character_locale", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_character_locale", request,
                            authorized=True)["executed"] is False
    handoff = registry.execute("studio_quest_character_locale", request,
                               authorized=True, dry_run=False)
    assert handoff["locale"] == "en-US"
    assert handoff["release_certified"] is False


def test_jeeves_localized_character_rejects_stale_and_mutated_input():
    parts = fixture()
    registry = CapabilityRegistry()
    register_quest_character_locale_tool(registry, *parts)
    request = {"expected_source_digest": compile_quest_program(parts[0]).source_digest,
               "expected_locale": "fr-FR"}
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_character_locale", request,
                         authorized=True, dry_run=False)
    parts[4]["authoring"]["rows"][0]["translation"] = "tampered"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_character_locale", {
            **request, "expected_locale": "en-US",
        }, authorized=True, dry_run=False)
