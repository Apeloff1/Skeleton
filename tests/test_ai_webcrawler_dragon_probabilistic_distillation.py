"""Tests for correlated rereads, contradictions, and provenance custody."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import (
    EvidencePass, EvidencePolicy, ProbabilisticKnowledgeDistiller,
)
from skeleton.ai.webcrawler.dragon_knowledge_ledger import (
    DragonKnowledgeLedger, schedule_rereads,
)


def evidence(source="s1", revision="v1", number=1, supports=True,
             group="publisher"):
    return EvidencePass(
        source, revision, f"pass-{number}", "jump-window",
        supports, 0.9, 0.9, group, f"frame:{number}",
        "A buffered input was observed",
    )


def test_repeated_readings_are_not_independent_confirmation():
    engine = ProbabilisticKnowledgeDistiller()
    one = engine.distill("jump-window", (evidence(),))
    many = engine.distill(
        "jump-window", tuple(evidence(number=i) for i in range(1, 7)),
    )
    assert one.probability == many.probability
    assert many.independent_groups == 1
    assert many.readings == 6


def test_independent_sources_can_increase_confidence():
    engine = ProbabilisticKnowledgeDistiller()
    correlated = engine.distill("jump-window", (evidence(),))
    independent = engine.distill("jump-window", (
        evidence(), evidence("s2", group="independent"),
    ))
    assert independent.probability > correlated.probability


def test_contradiction_is_preserved_and_flagged():
    engine = ProbabilisticKnowledgeDistiller()
    result = engine.distill("jump-window", (
        evidence(), evidence("s2", supports=False, group="other"),
    ))
    assert result.conflicting
    assert result.review_required
    assert result.supporting_groups == 1
    assert result.opposing_groups == 1


def test_minimum_reread_policy_requires_review():
    engine = ProbabilisticKnowledgeDistiller()
    assert engine.distill("jump-window", (evidence(),)).review_required
    assert engine.distill("jump-window", tuple(
        evidence(number=i) for i in (1, 2, 3)
    )).readings == 3


def test_invalid_probabilities_fail_closed():
    engine = ProbabilisticKnowledgeDistiller()
    from dataclasses import replace
    with pytest.raises(ValueError, match="confidence"):
        engine.distill("jump-window", (
            replace(evidence(), confidence=float("nan")),
        ))


def test_duplicate_pass_identity_rejected():
    engine = ProbabilisticKnowledgeDistiller()
    with pytest.raises(ValueError, match="duplicate"):
        engine.distill("jump-window", (evidence(), evidence()))


def test_source_budget_enforced():
    engine = ProbabilisticKnowledgeDistiller(
        EvidencePolicy(max_passes_per_source=3),
    )
    with pytest.raises(ValueError, match="budget"):
        engine.distill("jump-window", tuple(
            evidence(number=i) for i in range(4)
        ))


def test_lens_schedule_is_deterministic():
    a = schedule_rereads("source", "revision", minimum=3, maximum=8)
    assert a == schedule_rereads("source", "revision", minimum=3, maximum=8)
    assert len(a) == 8
    assert sum(x.required for x in a) == 3
    assert len({x.lens for x in a}) == 8


def test_ledger_owner_isolation_and_erasure():
    ledger = DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    ledger.add("alice", evidence(), authorized=True)
    ledger.add("bob", evidence(), authorized=True)
    assert len(ledger.readings("alice", "jump-window", authorized=True)) == 1
    assert ledger.erase("alice", authorized=True) == 1
    assert ledger.readings("alice", "jump-window", authorized=True) == ()
    assert len(ledger.readings("bob", "jump-window", authorized=True)) == 1


def test_ledger_rejects_mutating_same_evidence_identity():
    ledger = DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    ledger.add("alice", evidence(), authorized=True)
    ledger.add("alice", evidence(), authorized=True)
    with pytest.raises(ValueError, match="identity conflict"):
        ledger.add("alice", evidence(supports=False), authorized=True)


def test_evidence_requires_authorization():
    ledger = DragonKnowledgeLedger(sqlite3.connect(":memory:"))
    with pytest.raises(PermissionError):
        ledger.add("alice", evidence(), authorized=False)
    with pytest.raises(PermissionError):
        ledger.belief("alice", "jump-window", authorized=False)
