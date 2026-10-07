from __future__ import annotations

import math

import pytest

from skeleton.jeeves.agent.epistemic_frontier import (
    EpistemicFrontierEngine,
    GapKind,
    KnowledgeObligation,
    ProbeKind,
)
from skeleton.jeeves.agent.types import AgentContractError, RiskTier


def _obligation(**overrides):
    values = {
        "obligation_id": "deploy-safety",
        "question": "Is the candidate safe to deploy?",
        "decision_impact": 0.95,
        "confidence": 0.90,
        "evidence_coverage": 0.20,
        "freshness": 0.90,
        "contradiction_strength": 0.0,
        "model_disagreement": 0.0,
        "assumption_load": 0.0,
        "novelty": 0.30,
        "evidence_refs": ("ev-1",),
    }
    values.update(overrides)
    return KnowledgeObligation(**values)


def test_confident_but_uncovered_claim_becomes_blind_spot() -> None:
    engine = EpistemicFrontierEngine(clock=lambda: 100.0)
    snapshot = engine.discover([_obligation()])

    kinds = {gap.kind for gap in snapshot.gaps}
    assert GapKind.COVERAGE in kinds
    assert GapKind.BLIND_SPOT in kinds
    gap_by_id = {gap.gap_id: gap for gap in snapshot.gaps}
    blind_probe = next(
        probe
        for probe in snapshot.probes
        if gap_by_id[probe.gap_id].kind is GapKind.BLIND_SPOT
    )
    assert blind_probe.kind is ProbeKind.RED_TEAM_SEARCH
    assert snapshot.frontier_pressure > 0.0


def test_contradiction_and_disagreement_generate_falsifiable_probe_types() -> None:
    engine = EpistemicFrontierEngine()
    obligation = _obligation(
        confidence=0.55,
        evidence_coverage=0.85,
        contradiction_strength=0.82,
        model_disagreement=0.76,
    )
    snapshot = engine.discover([obligation])
    by_gap = {gap.gap_id: gap for gap in snapshot.gaps}
    kinds = {gap.kind for gap in snapshot.gaps}
    assert GapKind.CONTRADICTION in kinds
    assert GapKind.DISAGREEMENT in kinds

    probe_kinds = {
        by_gap[probe.gap_id].kind: probe.kind
        for probe in snapshot.probes
        if probe.gap_id in by_gap
    }
    assert probe_kinds[GapKind.CONTRADICTION] is ProbeKind.ADVERSARIAL_CHECK
    assert probe_kinds[GapKind.DISAGREEMENT] is ProbeKind.DISCRIMINATING_TEST


def test_probe_scoring_penalizes_risky_expensive_experiments() -> None:
    engine = EpistemicFrontierEngine()
    obligation = _obligation(
        confidence=0.50,
        evidence_coverage=0.90,
        contradiction_strength=0.70,
    )
    gap = next(
        item
        for item in engine.discover([obligation]).gaps
        if item.kind is GapKind.CONTRADICTION
    )
    safe = engine.propose_probe(
        gap,
        obligation,
        risk=RiskTier.READ_ONLY,
        expected_cost=0.10,
    )
    risky = engine.propose_probe(
        gap,
        obligation,
        risk=RiskTier.HIGH_IMPACT,
        expected_cost=1.00,
    )

    assert safe.expected_information_gain_bits == risky.expected_information_gain_bits
    assert safe.score > risky.score
    assert risky.preconditions


def test_precommitted_forecast_is_immutable_and_scores_without_hindsight() -> None:
    engine = EpistemicFrontierEngine(clock=lambda: 1234.0)
    contract = engine.precommit_forecast(
        "deploy-safety",
        {"safe": 0.8, "unsafe": 0.2},
        forecast_id="forecast-1",
    )
    settlement = engine.settle_forecast("forecast-1", "safe")

    assert contract.created_at == 1234.0
    assert len(contract.commitment) >= 32
    assert math.isclose(settlement.probability_assigned, 0.8)
    assert math.isclose(settlement.brier_score, 0.08)
    assert math.isclose(settlement.surprise_bits, -math.log2(0.8))

    with pytest.raises(AgentContractError):
        engine.precommit_forecast(
            "deploy-safety",
            {"safe": 0.9, "unsafe": 0.1},
            forecast_id="forecast-1",
        )


def test_frontier_snapshot_is_order_invariant_and_deterministic() -> None:
    engine = EpistemicFrontierEngine(clock=lambda: 1.0)
    first = _obligation(obligation_id="a", question="Question A?")
    second = _obligation(
        obligation_id="b",
        question="Question B?",
        confidence=0.4,
        evidence_coverage=0.7,
        model_disagreement=0.6,
    )

    left = engine.discover([first, second])
    right = engine.discover([second, first])

    assert left.fingerprint == right.fingerprint
    assert [item.gap_id for item in left.gaps] == [item.gap_id for item in right.gaps]
    assert [item.probe_id for item in left.probes] == [item.probe_id for item in right.probes]
