"""Jeeves typed branch adapters require explicit execution authority."""
from __future__ import annotations

import copy
import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_branch_jeeves import (
    register_quest_branch_review_tools,
)
from tests.test_studio_quest_branch_review import source


def test_registry_proposal_compile_and_guarded_handoff():
    docs = source()
    registry = CapabilityRegistry()
    meta = register_quest_branch_review_tools(registry, docs)
    assert len([x for x in registry.describe() if x["name"].startswith("studio_quest_branch_")]) == 3
    request = {
        "prompt": meta["prompt"],
        "left_actions": [["gate", "help"], ["harbor", "sail"]],
        "right_actions": [["gate", "ignore"], ["harbor", "stay"]],
        "target_ending": "rescue",
        "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_branch_propose", request,
                         authorized=False, dry_run=False)
    preview = registry.execute("studio_quest_branch_propose", request,
                               authorized=True, dry_run=True)
    assert preview["executed"] is False
    plan = registry.execute("studio_quest_branch_propose", request,
                            authorized=True, dry_run=False)
    plan["reviewed"] = True
    receipt = registry.execute("studio_quest_branch_compile", {
        "plan": plan, "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }, authorized=True, dry_run=False)
    assert len(receipt["canonical_counterfactual_digest"]) == 64
    handoff = registry.execute("studio_quest_branch_handoff", {
        "receipt": receipt,
    }, authorized=True, dry_run=False)
    assert handoff["target_ending"] == "rescue"
    assert handoff["release_certified"] is False


def test_registry_rejects_forged_payload_and_mutated_source():
    docs = source()
    registry = CapabilityRegistry()
    meta = register_quest_branch_review_tools(registry, docs)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_branch_propose", {
            "prompt": meta["prompt"], "target_ending": "rescue",
        }, authorized=True, dry_run=False)
    docs["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_branch_propose", {
            "prompt": meta["prompt"],
            "left_actions": [["gate", "help"]],
            "right_actions": [["gate", "ignore"]],
            "target_ending": "rescue",
            "expected_source_digest": meta["source_digest"],
            "expected_initial_session_digest": meta["initial_session_digest"],
        }, authorized=True, dry_run=False)


def test_identical_histories_do_not_masquerade_as_branch_comparison():
    docs = source()
    registry = CapabilityRegistry()
    meta = register_quest_branch_review_tools(registry, docs)
    plan = registry.execute("studio_quest_branch_propose", {
        "prompt": meta["prompt"],
        "left_actions": [["gate", "help"]],
        "right_actions": [["gate", "help"]],
        "target_ending": "rescue",
        "expected_source_digest": meta["source_digest"],
        "expected_initial_session_digest": meta["initial_session_digest"],
    }, authorized=True, dry_run=False)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_branch_compile", {
            "plan": plan, "expected_source_digest": meta["source_digest"],
            "expected_initial_session_digest": meta["initial_session_digest"],
        }, authorized=True, dry_run=False)
