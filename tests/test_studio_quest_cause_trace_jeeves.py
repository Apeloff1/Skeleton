"""Jeeves typed causal tools require authority, review and frozen source."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_cause_trace import PROMPT
from skeleton.ai.game_builder.studio_quest_cause_trace_jeeves import (
    register_quest_cause_tools,
)
from tests.test_studio_quest_character_locale import fixture


def test_typed_jeeves_proposal_compile_and_dry_run():
    documents = fixture()[0]
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    registry = CapabilityRegistry()
    register_quest_cause_tools(registry, documents)
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    request = {"prompt": PROMPT, "actions": actions,
               "expected_source_digest": program.source_digest,
               "expected_initial_session_digest": initial.digest}
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_cause_proposal", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_cause_proposal", request,
                            authorized=True)["executed"] is False
    plan = registry.execute("studio_quest_cause_proposal", request,
                            authorized=True, dry_run=False)
    assert plan["reviewed"] is False
    plan["reviewed"] = True
    receipt = registry.execute(
        "studio_quest_cause_compile",
        {"plan": plan, "expected_source_digest": program.source_digest,
         "expected_initial_session_digest": initial.digest},
        authorized=True, dry_run=False)
    assert receipt["authored_predicate_provenance_verified"] is True
    assert receipt["release_certified"] is False


def test_typed_jeeves_mutation_stale_and_malformed_rejected():
    documents = fixture()[0]
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    registry = CapabilityRegistry()
    register_quest_cause_tools(registry, documents)
    request = {"prompt": PROMPT, "actions": [],
               "expected_source_digest": program.source_digest,
               "expected_initial_session_digest": initial.digest}
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_cause_proposal",
                         {**request, "unexpected": True},
                         authorized=True, dry_run=False)
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_cause_proposal",
                         {**request, "expected_source_digest": "0" * 64},
                         authorized=True, dry_run=False)
    documents["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError, match="source changed"):
        registry.execute("studio_quest_cause_proposal", request,
                         authorized=True, dry_run=False)
