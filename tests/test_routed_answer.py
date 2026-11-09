"""A routed answer is billed per call and never quotes an empty model reply."""

import tempfile
from pathlib import Path

import pytest

from skeleton.intelligence.cascade import CascadeRouter, ModelResponse
from skeleton.intelligence.knowledge_base import KnowledgeBase, KnowledgeError
from skeleton.intelligence.routed_gate import RoutedGate, RoutedGateError
from skeleton.intelligence.uncertainty import Candidate, UncertaintyError, UncertaintyGate


def _router(cheap, strong) -> CascadeRouter:
    return CascadeRouter(cheap, strong, route_threshold=0.7, cheap_cost=1.0, strong_cost=10.0)


def test_samples_are_billed_and_an_empty_reply_abstains() -> None:
    calls = {"cheap": 0, "strong": 0}

    def cheap(query: str) -> ModelResponse:
        calls["cheap"] += 1
        return ModelResponse("the capital is paris", 0.9)

    def strong(query: str) -> ModelResponse:
        calls["strong"] += 1
        return ModelResponse("   ", 0.99)

    gate = RoutedGate(_router(cheap, strong), UncertaintyGate(), samples=3)
    answer = gate.answer("hello there")
    assert answer.abstained is False
    assert answer.model == "cheap"
    assert calls["cheap"] == 3
    assert gate.router.total_cost == 3.0

    hard = RoutedGate(_router(cheap, strong), UncertaintyGate())
    abstained = hard.answer("refactor the constraint?")
    assert abstained.abstained is True
    assert abstained.text == "I don't know."
    assert "   " not in abstained.text
    assert calls["strong"] == 1
    assert hard.router.total_cost == 10.0

    def boom(query: str) -> ModelResponse:
        raise RuntimeError("secret-trace")

    failed = RoutedGate(_router(boom, strong), UncertaintyGate(), samples=2)
    with pytest.raises(RuntimeError):
        failed.answer("hello there")
    assert failed.router.total_cost == 0.0
    with pytest.raises(ValueError):
        RoutedGate(_router(cheap, strong), UncertaintyGate(), samples=True)


def test_empty_agreement_and_bad_confidence_do_not_answer() -> None:
    gate = UncertaintyGate()
    decision = gate.decide([Candidate("   ", 0.95), Candidate("   ", 0.95)])
    assert decision.verdict.value == "abstain"
    assert decision.reason == "empty_answer"
    with pytest.raises(UncertaintyError):
        gate.decide([Candidate("yes", True)])  # type: ignore[arg-type]
    with pytest.raises(RoutedGateError):
        RoutedGate(
            _router(lambda query: ModelResponse("yes", 0.9), lambda query: ModelResponse("yes", 0.9)),
            UncertaintyGate(),
        ).answer("   ")


def test_search_returns_the_body_and_rejects_a_bad_id() -> None:
    with tempfile.TemporaryDirectory() as directory:
        kb = KnowledgeBase(root=Path(directory))
        kb.put("a", "Database failover", "How to fail over the database")
        kb.put("b", "Cache tuning", "Database connection pool sizing")
        hits = kb.search("database failover")
        assert hits[0]["doc_id"] == "a"
        assert hits[0]["body"] == "How to fail over the database"
        with pytest.raises(KnowledgeError):
            kb.put("../secret", "Title", "body")
        with pytest.raises(KnowledgeError):
            kb.put("note", "Title", "   ")
