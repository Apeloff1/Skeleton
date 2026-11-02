"""Jeeves dialogue localization requires explicit authority and exact leases."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_dialogue_localization_jeeves import (
    register_dialogue_localization_tools,
)
from tests.test_studio_quest_dialogue_localization import fixture


def test_jeeves_localization_authorized_compile_handoff():
    docs, program, initial, npc, dialogue, _ = fixture()
    registry = CapabilityRegistry()
    meta = register_dialogue_localization_tools(registry, docs, npc, dialogue)
    request = {
        "prompt": meta["prompt"], "locale": "fr-FR",
        "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }
    with pytest.raises(PermissionError):
        registry.execute("studio_dialogue_locale_propose", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_dialogue_locale_propose", request,
                            authorized=True)["executed"] is False
    plan = registry.execute("studio_dialogue_locale_propose", request,
                            authorized=True, dry_run=False)
    for row in plan["rows"]:
        row["translation"] = "Une ligne originale"
        row["reviewed"] = True
    receipt = registry.execute("studio_dialogue_locale_compile", {
        "plan": plan, "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }, authorized=True, dry_run=False)
    handoff = registry.execute("studio_dialogue_locale_handoff", {
        "receipt": receipt,
    }, authorized=True, dry_run=False)
    assert handoff["locale"] == "fr-FR"
    assert handoff["release_certified"] is False


def test_jeeves_localization_rejects_source_mutation():
    docs, program, initial, npc, dialogue, _ = fixture()
    registry = CapabilityRegistry()
    meta = register_dialogue_localization_tools(registry, docs, npc, dialogue)
    dialogue["authoring"]["lines"][0]["text"] = "tampered"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_dialogue_locale_propose", {
            "prompt": meta["prompt"], "locale": "fr-FR",
            "expected_source_digest": meta["source_digest"],
            "expected_initial_session_digest": meta["initial_session_digest"],
        }, authorized=True, dry_run=False)
