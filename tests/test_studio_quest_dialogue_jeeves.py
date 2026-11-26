"""Jeeves dialogue capability authorization, lease and handoff."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_dialogue_jeeves import (
    register_quest_dialogue_tools,
)
from tests.test_studio_quest_npc_relationships import fixture, compile_plan


def test_jeeves_dialogue_typed_end_to_end():
    docs, program, initial, npc_plan = fixture()
    npc = compile_plan(docs, program, initial, npc_plan)
    registry = CapabilityRegistry()
    meta = register_quest_dialogue_tools(registry, docs, npc)
    proposal = {
        "prompt": meta["prompt"],
        "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_dialogue_propose", proposal,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_dialogue_propose", proposal,
                            authorized=True)["executed"] is False
    plan = registry.execute("studio_quest_dialogue_propose", proposal,
                            authorized=True, dry_run=False)
    for row in plan["lines"]:
        row["speaker"] = "captain"
        row["text"] = "An original line"
        row["reviewed"] = True
    receipt = registry.execute("studio_quest_dialogue_compile", {
        "plan": plan, "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }, authorized=True, dry_run=False)
    handoff = registry.execute("studio_quest_dialogue_handoff", {
        "receipt": receipt,
    }, authorized=True, dry_run=False)
    assert handoff["dialogue_digest"] == receipt["dialogue_digest"]
    assert handoff["release_certified"] is False


def test_jeeves_dialogue_rejects_malformed_and_stale_receipts():
    docs, program, initial, npc_plan = fixture()
    npc = compile_plan(docs, program, initial, npc_plan)
    registry = CapabilityRegistry()
    meta = register_quest_dialogue_tools(registry, docs, npc)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_dialogue_propose", {
            "prompt": meta["prompt"],
        }, authorized=True, dry_run=False)
    npc["final_trust"][0]["trust"] = 100
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_dialogue_propose", {
            "prompt": meta["prompt"],
            "expected_source_digest": meta["source_digest"],
            "expected_initial_session_digest": meta["initial_session_digest"],
        }, authorized=True, dry_run=False)
