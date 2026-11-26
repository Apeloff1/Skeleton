"""Jeeves NPC relationship capability authorization and source leases."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_npc_jeeves import (
    register_quest_npc_relationship_tools,
)
from tests.test_studio_quest_branch_review import source


def test_typed_npc_jeeves_proposal_compile_handoff():
    docs = source()
    registry = CapabilityRegistry()
    meta = register_quest_npc_relationship_tools(registry, docs)
    proposal = {
        "prompt": meta["prompt"], "actors": ["captain"],
        "actions": [["gate", "help"], ["harbor", "sail"]],
        "target_ending": "rescue",
        "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_npc_propose", proposal,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_npc_propose", proposal,
                            authorized=True)["executed"] is False
    plan = registry.execute("studio_quest_npc_propose", proposal,
                            authorized=True, dry_run=False)
    plan["actors"][0]["reviewed"] = True
    plan["effects"] = [{
        "stage_id": "gate", "choice": "help", "actor_id": "captain",
        "delta": 10, "reason": "A witnessed act of kindness", "reviewed": True,
    }]
    receipt = registry.execute("studio_quest_npc_compile", {
        "plan": plan, "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }, authorized=True, dry_run=False)
    handoff = registry.execute("studio_quest_npc_handoff", {
        "receipt": receipt,
    }, authorized=True, dry_run=False)
    assert handoff["final_trust"] == [{"actor_id": "captain", "trust": 10}]
    assert handoff["native_gameplay_verified"] is False


def test_npc_jeeves_rejects_malformed_requests_and_source_drift():
    docs = source()
    registry = CapabilityRegistry()
    meta = register_quest_npc_relationship_tools(registry, docs)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_npc_propose", {"prompt": meta["prompt"]},
                         authorized=True, dry_run=False)
    docs["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_npc_propose", {
            "prompt": meta["prompt"], "actors": ["captain"],
            "actions": [], "target_ending": "rescue",
            "expected_source_digest": meta["source_digest"],
            "expected_initial_session_digest": meta["initial_session_digest"],
        }, authorized=True, dry_run=False)
