from __future__ import annotations

from skeleton.jeeves.agent.deliberation import (
    CandidateProposal,
    CandidateScore,
    DeliberationMode,
    SearchResult,
    SpecialistRole,
)
from skeleton.jeeves.agent.epistemic_frontier import GapKind, ProbeKind
from skeleton.jeeves.agent.frontier_probe_planning import FrontierProbePlanner
from skeleton.jeeves.agent.frontier_reasoning import (
    FrontierReasoningCoordinator,
    InferenceDisposition,
)
from skeleton.jeeves.agent.types import (
    EvidenceKind,
    EvidenceRef,
    stable_fingerprint,
)


def _evidence(name: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"evidence:{name}",
        kind=EvidenceKind.FIXTURE,
        source="frontier-probe-test",
        fingerprint=stable_fingerprint({"evidence": name}),
        confidence=0.9,
        observed_at=1.0,
    )


def _candidate(
    name: str,
    *,
    action: str,
    outcome: str,
    confidence: float = 0.9,
    evidence: tuple[EvidenceRef, ...] = (),
    assumptions: tuple[str, ...] = (),
) -> CandidateProposal:
    return CandidateProposal(
        candidate_id=f"candidate:{name}",
        parent_id=None,
        depth=0,
        role=SpecialistRole.SOLVER,
        summary=f"candidate {name}",
        proposed_action=action,
        predicted_outcome=outcome,
        confidence=confidence,
        evidence=evidence,
        assumptions=assumptions,
    )


def _score(
    candidate: CandidateProposal,
    *,
    total: float = 0.9,
    evidence_quality: float = 0.9,
    verifier: float = 0.9,
) -> CandidateScore:
    return CandidateScore(
        candidate_id=candidate.candidate_id,
        utility=total,
        evidence_quality=evidence_quality,
        confidence_quality=candidate.confidence,
        risk_penalty=0.05,
        cost_penalty=0.0,
        novelty_bonus=0.5,
        verifier_score=verifier,
        total=total,
        reasons=(),
    )


def _search(*pairs: tuple[CandidateProposal, CandidateScore]) -> SearchResult:
    return SearchResult(
        mode=DeliberationMode.COMMITTEE,
        best=pairs[0][0] if pairs else None,
        ranking=tuple(pairs),
        explored=tuple(candidate for candidate, _ in pairs),
        ledger={"model_calls": 2, "candidates": len(pairs)},
        stopped_reason="fixture",
        trace_fingerprint=stable_fingerprint(
            [candidate.candidate_id for candidate, _ in pairs]
        ),
    )


def test_low_evidence_decision_produces_retrieval_probe() -> None:
    candidate = _candidate(
        "weak-evidence",
        action="answer now",
        outcome="answer is accepted",
        confidence=0.96,
    )
    decision = FrontierReasoningCoordinator().decide(
        _search(
            (
                candidate,
                _score(
                    candidate,
                    total=0.95,
                    evidence_quality=0.10,
                    verifier=0.95,
                ),
            )
        )
    )

    plan = FrontierProbePlanner().plan(decision)

    assert decision.disposition is InferenceDisposition.SEEK_EVIDENCE
    assert any(gap.kind is GapKind.COVERAGE for gap in plan.gaps)
    assert any(probe.kind is ProbeKind.RETRIEVAL for probe in plan.probes)
    assert plan.obligation.evidence_coverage == 0.10
    assert plan.selected_probe is not None


def test_candidate_disagreement_produces_discriminating_probe() -> None:
    evidence = (_evidence("shared"),)
    left = _candidate(
        "left",
        action="choose alpha",
        outcome="alpha succeeds",
        evidence=evidence,
    )
    right = _candidate(
        "right",
        action="choose beta",
        outcome="beta succeeds",
        evidence=evidence,
    )
    decision = FrontierReasoningCoordinator().decide(
        _search(
            (left, _score(left, total=0.90)),
            (right, _score(right, total=0.89)),
        )
    )

    plan = FrontierProbePlanner().plan(decision)

    assert decision.disposition is InferenceDisposition.DELIBERATE
    assert plan.obligation.model_disagreement > 0.40
    assert any(gap.kind is GapKind.DISAGREEMENT for gap in plan.gaps)
    assert any(
        probe.kind is ProbeKind.DISCRIMINATING_TEST
        for probe in plan.probes
    )


def test_explicit_assumptions_produce_falsification_probe() -> None:
    candidate = _candidate(
        "assumption-heavy",
        action="apply guarded adapter",
        outcome="compatibility remains intact",
        evidence=(_evidence("adapter"),),
        assumptions=(
            "legacy callers preserve argument order",
            "schema remains backward compatible",
            "provider metadata is stable",
            "no hidden side effect is introduced",
        ),
    )
    decision = FrontierReasoningCoordinator().decide(
        _search((candidate, _score(candidate)))
    )

    plan = FrontierProbePlanner().plan(decision)

    assert plan.obligation.assumption_load == 1.0
    assert any(gap.kind is GapKind.ASSUMPTION for gap in plan.gaps)
    assert any(probe.kind is ProbeKind.FALSIFICATION for probe in plan.probes)


def test_frontier_probe_plan_is_replay_deterministic() -> None:
    candidate = _candidate(
        "deterministic",
        action="verify bounded change",
        outcome="verified behavior remains stable",
        evidence=(_evidence("deterministic"),),
    )
    decision = FrontierReasoningCoordinator().decide(
        _search((candidate, _score(candidate)))
    )
    planner = FrontierProbePlanner()

    first = planner.plan(decision)
    second = planner.plan(decision)

    assert first.fingerprint == second.fingerprint
    assert first.obligation.fingerprint == second.obligation.fingerprint
    assert tuple(item.fingerprint for item in first.probes) == tuple(
        item.fingerprint for item in second.probes
    )
