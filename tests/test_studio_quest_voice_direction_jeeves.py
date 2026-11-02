"""Typed Jeeves voice direction permission and mutation tests."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_character_locale import (
    compile_quest_character_locale_handoff,
)
from skeleton.ai.game_builder.studio_quest_voice_direction import PROMPT
from skeleton.ai.game_builder.studio_quest_voice_direction_jeeves import (
    register_quest_voice_direction_tools,
)
from tests.test_studio_quest_character_locale import fixture


def test_jeeves_proposal_and_compile_require_authority_and_review():
    parts = fixture()
    base = compile_quest_character_locale_handoff(*parts, authorized=True)
    registry = CapabilityRegistry()
    register_quest_voice_direction_tools(registry, *parts)
    request = {"prompt": PROMPT,
               "expected_handoff_digest": base["handoff_digest"]}
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_voice_proposal", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_voice_proposal", request,
                            authorized=True)["executed"] is False
    plan = registry.execute("studio_quest_voice_proposal", request,
                            authorized=True, dry_run=False)
    for row in plan["rows"]:
        row["reviewed"] = True
    receipt = registry.execute(
        "studio_quest_voice_compile",
        {"plan": plan, "expected_handoff_digest": base["handoff_digest"]},
        authorized=True, dry_run=False)
    assert receipt["canonical_quest_replay_verified"] is True
    assert receipt["audio_generated"] is False


def test_jeeves_rejects_stale_lease_and_mutated_source():
    parts = fixture()
    base = compile_quest_character_locale_handoff(*parts, authorized=True)
    registry = CapabilityRegistry()
    register_quest_voice_direction_tools(registry, *parts)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_voice_proposal", {
            "prompt": PROMPT, "expected_handoff_digest": "0" * 64,
        }, authorized=True, dry_run=False)
    parts[0]["quest"]["stage_graph"][0]["reward"] = "tampered"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_voice_proposal", {
            "prompt": PROMPT,
            "expected_handoff_digest": base["handoff_digest"],
        }, authorized=True, dry_run=False)
