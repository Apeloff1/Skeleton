from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.eval.benchmark_registry import BenchmarkQualificationDecision
from skeleton.eval.regression_corpus import (
    FailureClass,
    RegressionCase,
    RegressionCorpus,
    RegressionCorpusError,
    RegressionObservation,
    SafeOutcome,
    qualify_regression_corpus as _qualify_regression_corpus,
)


CANDIDATE = "a" * 64


def _benchmark(
    *,
    accepted: bool = True,
    benchmark_manifest_digest: str = "1" * 64,
) -> BenchmarkQualificationDecision:
    return BenchmarkQualificationDecision(
        accepted=accepted,
        reasons=() if accepted else ("forced-rejection",),
        benchmark_manifest_digest=benchmark_manifest_digest,
        experiment_manifest_digest="2" * 64,
        reproducibility_bundle_digest="3" * 64,
        evaluated_split_ids=("regression",),
    )


def _qualify(
    *,
    benchmark: BenchmarkQualificationDecision | None = None,
    expected_benchmark_digest: str | None = None,
    **kwargs,
):
    benchmark = benchmark or _benchmark()
    return _qualify_regression_corpus(
        benchmark_qualification=benchmark,
        expected_benchmark_qualification_digest=(
            benchmark.decision_digest
            if expected_benchmark_digest is None
            else expected_benchmark_digest
        ),
        **kwargs,
    )


def _case(
    case_id: str,
    failure_class: FailureClass,
    outcome: SafeOutcome,
    *,
    fill: str,
) -> RegressionCase:
    return RegressionCase(
        case_id=case_id,
        version=1,
        failure_class=failure_class,
        description=f"Regression for {case_id}.",
        source_ref=f"incident:{case_id}",
        source_digest=fill * 64,
        input_digest=chr(ord(fill) + 1) * 64,
        expected_outcome=outcome,
        evaluator_id="independent-regression-evaluator",
        evaluator_digest="e" * 64,
        risk_obligation_id=f"P1-ADVERSARIAL-{case_id}",
        risk_obligation_digest=chr(ord(fill) + 2) * 64,
        tags=("promotion", "red-team"),
    )


def _corpus() -> RegressionCorpus:
    return RegressionCorpus(
        corpus_id="p1-known-failures",
        version=1,
        cases=(
            _case(
                "spec-game-001",
                FailureClass.SPECIFICATION_GAMING,
                SafeOutcome.REJECT,
                fill="1",
            ),
            _case(
                "reasoning-001",
                FailureClass.REASONING_ERROR,
                SafeOutcome.SAFE_COMPLETE,
                fill="4",
            ),
            _case(
                "side-effect-001",
                FailureClass.SIDE_EFFECT_ESCAPE,
                SafeOutcome.NO_SIDE_EFFECT,
                fill="7",
            ),
        ),
    )


def _observation(
    case: RegressionCase,
    *,
    outcome: SafeOutcome | None = None,
    candidate_digest: str = CANDIDATE,
    evaluator_id: str | None = None,
    evaluator_digest: str | None = None,
) -> RegressionObservation:
    return RegressionObservation(
        case_digest=case.case_digest,
        candidate_digest=candidate_digest,
        actual_outcome=case.expected_outcome if outcome is None else outcome,
        evaluator_id=case.evaluator_id if evaluator_id is None else evaluator_id,
        evaluator_digest=(
            case.evaluator_digest
            if evaluator_digest is None
            else evaluator_digest
        ),
        output_digest="b" * 64,
        evidence_refs=(
            EvidenceRef(
                source=f"regression://{case.case_id}",
                digest="c" * 64,
                category="regression",
            ),
        ),
        independent=True,
        side_effect_count=0,
    )


def _risk(
    case: RegressionCase,
    *,
    resolved: bool = True,
    blocking: bool = True,
    blockers: tuple[str, ...] = (),
    obligation_digest: str | None = None,
) -> RiskBindingEvaluation:
    return RiskBindingEvaluation(
        obligation_id=case.risk_obligation_id,
        obligation_digest=(
            case.risk_obligation_digest
            if obligation_digest is None
            else obligation_digest
        ),
        resolved=resolved,
        blocking=blocking,
        severity="high",
        disposition="evidence",
        blockers=blockers,
    )


def _clean():
    corpus = _corpus()
    observations = tuple(_observation(case) for case in corpus.cases)
    risks = {
        case.risk_obligation_id: _risk(case)
        for case in corpus.cases
    }
    return corpus, observations, risks


def test_complete_clean_regression_corpus_qualifies() -> None:
    corpus, observations, risks = _clean()

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=risks,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert set(decision.passed_case_digests) == {
        case.case_digest for case in corpus.cases
    }
    assert decision.failed_case_digests == ()
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "regression_corpus_qualification"
    assert evidence.digest == decision.decision_digest


def test_missing_case_blocks_promotion() -> None:
    corpus, observations, risks = _clean()

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations[:-1],
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "regression-case-missing:side-effect-001" in decision.reasons
    assert corpus.cases[-1].case_digest in decision.failed_case_digests


def test_reappearing_known_failure_blocks_promotion() -> None:
    corpus, observations, risks = _clean()
    broken = replace(
        observations[0],
        actual_outcome=SafeOutcome.SAFE_COMPLETE,
    )

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=(broken, *observations[1:]),
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert any(
        reason.startswith("regression-reappeared:spec-game-001:")
        for reason in decision.reasons
    )
    assert corpus.cases[0].case_digest in decision.failed_case_digests


def test_candidate_substitution_marks_case_failed() -> None:
    corpus, observations, risks = _clean()
    substituted = replace(
        observations[1],
        candidate_digest="0" * 64,
    )

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=(
            observations[0],
            substituted,
            observations[2],
        ),
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "candidate-digest-mismatch:reasoning-001" in decision.reasons
    assert corpus.cases[1].case_digest in decision.failed_case_digests
    assert corpus.cases[1].case_digest not in decision.passed_case_digests


def test_evaluator_substitution_blocks() -> None:
    corpus, observations, risks = _clean()
    substituted = replace(
        observations[0],
        evaluator_id="self-evaluator",
        evaluator_digest="0" * 64,
    )

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=(substituted, *observations[1:]),
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "evaluator-id-mismatch:spec-game-001" in decision.reasons
    assert "evaluator-digest-mismatch:spec-game-001" in decision.reasons


def test_missing_or_unresolved_evid04_binding_blocks() -> None:
    corpus, observations, risks = _clean()
    missing = dict(risks)
    missing.pop(corpus.cases[0].risk_obligation_id)

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=missing,
    )
    assert decision.accepted is False
    assert "risk-evaluation-missing:spec-game-001" in decision.reasons

    unresolved = dict(risks)
    unresolved[corpus.cases[1].risk_obligation_id] = _risk(
        corpus.cases[1],
        resolved=False,
        blockers=("binding review is overdue",),
    )
    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=unresolved,
    )
    assert decision.accepted is False
    assert "risk-binding-unresolved:reasoning-001" in decision.reasons


def test_nonblocking_risk_binding_cannot_back_promotion_regression() -> None:
    corpus, observations, risks = _clean()
    risks = dict(risks)
    risks[corpus.cases[2].risk_obligation_id] = _risk(
        corpus.cases[2],
        blocking=False,
    )

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "risk-not-promotion-blocking:side-effect-001" in decision.reasons


def test_risk_obligation_digest_substitution_blocks() -> None:
    corpus, observations, risks = _clean()
    risks = dict(risks)
    risks[corpus.cases[0].risk_obligation_id] = _risk(
        corpus.cases[0],
        obligation_digest="0" * 64,
    )

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "risk-obligation-digest-mismatch:spec-game-001" in decision.reasons


def test_duplicate_and_unknown_observations_fail_closed() -> None:
    corpus, observations, risks = _clean()

    duplicate = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=(*observations, observations[0]),
        risk_evaluations=risks,
    )
    assert duplicate.accepted is False
    assert "regression-case-duplicate:spec-game-001" in duplicate.reasons

    unknown = replace(
        observations[0],
        case_digest="0" * 64,
    )
    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=(unknown, *observations[1:]),
        risk_evaluations=risks,
    )
    assert decision.accepted is False
    assert "unknown-regression-observation:" + ("0" * 64) in decision.reasons
    assert "regression-case-missing:spec-game-001" in decision.reasons


def test_observation_cannot_create_side_effects_or_self_evaluate() -> None:
    case = _corpus().cases[0]

    with pytest.raises(RegressionCorpusError, match="cannot create side effects"):
        replace(_observation(case), side_effect_count=1)

    with pytest.raises(
        RegressionCorpusError,
        match="must be independent",
    ):
        replace(_observation(case), independent=False)


def test_case_must_remain_promotion_blocking() -> None:
    with pytest.raises(
        RegressionCorpusError,
        match="must be promotion blocking",
    ):
        replace(_corpus().cases[0], promotion_blocking=False)


def test_corpus_digest_is_independent_of_case_tuple_order() -> None:
    corpus = _corpus()
    reversed_corpus = RegressionCorpus(
        corpus_id=corpus.corpus_id,
        version=corpus.version,
        cases=tuple(reversed(corpus.cases)),
    )
    assert reversed_corpus.corpus_digest == corpus.corpus_digest


def test_rejected_qualification_cannot_materialize_evidence() -> None:
    corpus, observations, risks = _clean()
    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations[:-1],
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    with pytest.raises(RegressionCorpusError, match="cannot become promotion"):
        decision.accepted_evidence_ref()

def test_rejected_learn02_benchmark_blocks_regression_promotion() -> None:
    corpus, observations, risks = _clean()
    rejected = _benchmark(accepted=False)

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=risks,
        benchmark=rejected,
    )

    assert decision.accepted is False
    assert "benchmark-qualification-rejected" in decision.reasons
    assert (
        decision.benchmark_qualification_digest
        == rejected.decision_digest
    )


def test_learn02_benchmark_substitution_blocks() -> None:
    corpus, observations, risks = _clean()
    benchmark = _benchmark()

    decision = _qualify(
        corpus=corpus,
        candidate_digest=CANDIDATE,
        observations=observations,
        risk_evaluations=risks,
        benchmark=benchmark,
        expected_benchmark_digest="0" * 64,
    )

    assert decision.accepted is False
    assert "benchmark-qualification-digest-mismatch" in decision.reasons
