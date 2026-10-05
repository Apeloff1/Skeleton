"""Tests for the routed gate — uncertainty + cascade composition."""

from __future__ import annotations

import pytest

from skeleton.intelligence.cascade import CascadeRouter, ModelResponse
from skeleton.intelligence.routed_gate import RoutedGate
from skeleton.intelligence.uncertainty import UncertaintyGate


def _models(cheap_conf):
    cheap = lambda q: ModelResponse(text="cheap answer", confidence=cheap_conf)
    strong = lambda q: ModelResponse(text="strong answer", confidence=0.95)
    return cheap, strong


def _gate_router(cheap_conf, **router_kwargs):
    cheap, strong = _models(cheap_conf)
    router = CascadeRouter(cheap, strong, **router_kwargs)
    return RoutedGate(router, UncertaintyGate())


def test_confident_candidates_answer_cheap():
    rg = _gate_router(0.9)
    a = rg.answer("what is a vector")
    assert a.model == "cheap" and not a.abstained
    assert a.text == "cheap answer"


def test_divergent_candidates_abstain():
    cheap = lambda q: ModelResponse(text=f"option {id(q) % 3}", confidence=0.55)
    strong = lambda q: ModelResponse(text="strong", confidence=0.95)
    # force divergence by varying text per call
    calls = {"n": 0}
    def varied(q):
        calls["n"] += 1
        return ModelResponse(text=f"answer_{calls['n']}", confidence=0.55)
    rg = RoutedGate(CascadeRouter(varied, strong), UncertaintyGate())
    a = rg.answer("ambiguous question")
    assert a.abstained and a.model == "none"
    assert rg.stats()["abstained"] == 1


def test_low_confidence_escalates_to_strong():
    rg = _gate_router(0.2)
    a = rg.answer("what is a vector")
    assert a.model == "strong" and a.escalated
    assert rg.router.escalations == 1


def test_hard_query_skips_sampling():
    rg = _gate_router(0.9, route_threshold=0.3)
    a = rg.answer("Prove and formally derive the constraint theorem")
    assert a.model == "strong" and a.verdict == "difficulty_direct"
    assert not a.escalated


def test_stats_compose_router_and_gate():
    rg = _gate_router(0.9)
    rg.answer("one")
    rg.answer("two")
    stats = rg.stats()
    assert stats["queries"] == 2
    assert "router" in stats and "gate" in stats
    assert stats["router"]["cost_vs_all_strong"] < 0.5
