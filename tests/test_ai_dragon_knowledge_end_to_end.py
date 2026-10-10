"""Cross-plane integration tests: evidence -> belief -> promotion -> retrieval.

Exercises the real module contracts rather than mocked layer outputs.
"""
import sqlite3

from skeleton.ai.webcrawler.dragon_knowledge_ledger import DragonKnowledgeLedger
from skeleton.ai.webcrawler.dragon_knowledge_graph import (
    DragonKnowledgeGraph, KnowledgeConcept, KnowledgeRelation, Relation,
)
from skeleton.ai.webcrawler.dragon_knowledge_retrieval import retrieve_knowledge
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass
from skeleton.ai.webcrawler.dragon_belief_stress import stress_test_belief
from skeleton.ai.webcrawler.dragon_adaptive_rereads import plan_adaptive_rereads
from skeleton.ai.webcrawler.dragon_knowledge_promotion import (
    PromotionPolicy, assess_promotion,
)


def _reading(source, pass_index, supports=True):
    return EvidencePass(
        source_id=source,
        source_revision="recording-sha256-v1",
        pass_id=f"pass-{pass_index}",
        claim_id="mechanic:jump_buffering",
        supports=supports,
        confidence=0.95,
        reliability=0.95,
        independence_group=source,
        evidence_locator=f"frame:{pass_index}",
        observation="Early input precedes observed landing jump",
    )


def test_evidence_to_retrieval_without_fabricated_certainty():
    db = sqlite3.connect(":memory:")
    ledger = DragonKnowledgeLedger(db)
    graph = DragonKnowledgeGraph(db)
    for source in ("capture-a", "capture-b", "capture-c"):
        for i in (1, 2, 3):
            ledger.add("alice", _reading(source, i), authorized=True)
    belief = ledger.belief(
        "alice", "mechanic:jump_buffering", authorized=True,
    )
    assert belief.independent_groups == 3
    assert belief.readings == 9
    assert not belief.conflicting
    report = stress_test_belief(
        belief.claim_id,
        ledger.readings("alice", belief.claim_id, authorized=True),
        authorized=True,
    )
    assert report.independent_groups == 3
    decision = assess_promotion(
        belief.claim_id,
        ledger.readings("alice", belief.claim_id, authorized=True),
        (), (), authorized=True,
    )
    assert not decision.eligible
    assert "Analysis chain is incomplete" in decision.reasons

    # Graph insertion is deliberately separate from memory promotion.
    # A discoverable hypothesis is not automatically certified knowledge.
    graph.put_concept("alice", KnowledgeConcept(
        belief.claim_id, "platforming",
        "Hypothesis: jump input may be buffered before landing",
    ), authorized=True)
    snapshot = retrieve_knowledge(
        graph, "alice", "jump input", authorized=True,
    )
    assert len(snapshot.hits) == 1
    assert "Hypothesis" in snapshot.hits[0].statement


def test_conflicting_evidence_triggers_analysis_and_review():
    db = sqlite3.connect(":memory:")
    ledger = DragonKnowledgeLedger(db)
    for source, polarity in (("a", True), ("b", False)):
        for index in (1, 2, 3):
            ledger.add("alice", _reading(source, index, polarity),
                       authorized=True)
    belief = ledger.belief(
        "alice", "mechanic:jump_buffering", authorized=True,
    )
    assert belief.conflicting
    stress = stress_test_belief(
        belief.claim_id,
        ledger.readings("alice", belief.claim_id, authorized=True),
        authorized=True,
    )
    assert stress.requires_adversarial_review
    assert plan_adaptive_rereads(
        belief, ledger.readings("alice", belief.claim_id, authorized=True),
        authorized=True,
    )
    decision = assess_promotion(
        belief.claim_id,
        ledger.readings("alice", belief.claim_id, authorized=True),
        (), (), authorized=True,
        policy=PromotionPolicy(require_full_analysis=False),
    )
    assert not decision.eligible
    assert any("Contradictory" in x for x in decision.reasons)


def test_erasure_cascades_through_owner_scoped_evidence_and_graph():
    db = sqlite3.connect(":memory:")
    ledger = DragonKnowledgeLedger(db)
    graph = DragonKnowledgeGraph(db)
    ledger.add("alice", _reading("capture-a", 1), authorized=True)
    ledger.add("bob", _reading("capture-b", 1), authorized=True)
    graph.put_concept("alice", KnowledgeConcept(
        "jump", "mechanics", "Jump buffering",
    ), authorized=True)
    assert ledger.erase("alice", authorized=True) == 1
    assert graph.erase("alice", authorized=True) == 1
    assert not ledger.readings(
        "alice", "mechanic:jump_buffering", authorized=True,
    )
    assert len(ledger.readings(
        "bob", "mechanic:jump_buffering", authorized=True,
    )) == 1
