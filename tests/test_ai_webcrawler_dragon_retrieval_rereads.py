"""Adaptive reread and knowledge retrieval regression tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_adaptive_rereads import (
    plan_adaptive_rereads,
)
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import (
    EvidencePass, ProbabilisticKnowledgeDistiller,
)
from skeleton.ai.webcrawler.dragon_knowledge_graph import (
    DragonKnowledgeGraph, KnowledgeConcept,
)
from skeleton.ai.webcrawler.dragon_knowledge_retrieval import retrieve_knowledge


def evidence(number=1, supports=True):
    return EvidencePass(
        "game-video", "revision-1", f"pass-{number}",
        "jump-buffer", supports, 0.8, 0.9, "same-video",
        f"frame:{number}", "Player jumped after early input",
    )


def test_reread_planner_prioritizes_missing_coverage():
    readings = (evidence(),)
    belief = ProbabilisticKnowledgeDistiller().distill(
        "jump-buffer", readings,
    )
    decisions = plan_adaptive_rereads(
        belief, readings, authorized=True,
    )
    assert decisions[0].next_pass.pass_index == 2
    assert decisions[0].reason == "minimum coverage"


def test_reread_planner_exhaustion():
    readings = tuple(evidence(number=i) for i in (1, 2, 3))
    belief = ProbabilisticKnowledgeDistiller().distill(
        "jump-buffer", readings,
    )
    decisions = plan_adaptive_rereads(
        belief, readings, authorized=True, max_passes=3,
    )
    assert decisions[0].exhausted


def test_reread_planner_preserves_claim_scope():
    readings = (evidence(),)
    belief = ProbabilisticKnowledgeDistiller().distill(
        "jump-buffer", readings,
    )
    from dataclasses import replace
    with pytest.raises(ValueError, match="cross-claim"):
        plan_adaptive_rereads(
            belief, (replace(evidence(), claim_id="other"),),
            authorized=True,
        )


def graph():
    result = DragonKnowledgeGraph(sqlite3.connect(":memory:"))
    result.put_concept(
        "alice", KnowledgeConcept(
            "jump-buffer", "platforming",
            "Early jump input remains buffered briefly",
        ), authorized=True,
    )
    result.put_concept(
        "alice", KnowledgeConcept(
            "camera-easing", "camera",
            "Smooth camera motion supports readability",
        ), authorized=True,
    )
    return result


def test_retrieval_is_deterministic():
    g = graph()
    a = retrieve_knowledge(g, "alice", "jump platforming", authorized=True)
    b = retrieve_knowledge(g, "alice", "jump platforming", authorized=True)
    assert a == b
    assert a.hits[0].concept_id == "jump-buffer"


def test_retrieval_owner_isolation():
    g = graph()
    assert not retrieve_knowledge(
        g, "bob", "jump", authorized=True,
    ).hits


def test_retrieval_fingerprint_changes_with_graph():
    g = graph()
    before = retrieve_knowledge(g, "alice", "jump", authorized=True)
    g.put_concept(
        "alice", KnowledgeConcept("new", "platforming", "Jump timing"),
        authorized=True,
    )
    after = retrieve_knowledge(g, "alice", "jump", authorized=True)
    assert before.graph_fingerprint != after.graph_fingerprint
    assert before.retrieval_fingerprint != after.retrieval_fingerprint


def test_retrieval_scan_budget():
    g = graph()
    with pytest.raises(ValueError, match="budget"):
        retrieve_knowledge(
            g, "alice", "jump", authorized=True, max_scan=1,
        )


def test_retrieval_requires_authorization():
    with pytest.raises(PermissionError):
        retrieve_knowledge(
            graph(), "alice", "jump", authorized=False,
        )
