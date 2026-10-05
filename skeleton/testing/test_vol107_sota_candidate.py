from __future__ import annotations

from dataclasses import replace
import math

import pytest

from skeleton.eval.sota_candidate import (
    SOTA_CANDIDATE_CLAIM,
    SOTACandidateClaim,
    SOTACandidateError,
    SOTACandidateGate,
    SOTAMetricDirection,
    SOTAMetricRequirement,
    SOTAReplayRecord,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
REVISION = "1" * 40


def requirements() -> tuple[SOTAMetricRequirement, ...]:
    return (
        SOTAMetricRequirement(
            metric_id="correctness",
            direction=SOTAMetricDirection.MAXIMIZE,
            baseline_value=0.80,
            minimum_delta=0.05,
        ),
        SOTAMetricRequirement(
            metric_id="latency_ms",
            direction=SOTAMetricDirection.MINIMIZE,
            baseline_value=100.0,
            minimum_delta=5.0,
        ),
    )


def claim(**overrides) -> SOTACandidateClaim:
    values = {
        "claim_id": "claim-1",
        "candidate_id": "candidate-1",
        "benchmark_id": "benchmark-1",
        "benchmark_digest": SHA_A,
        "dataset_digest": SHA_B,
        "source_revision": REVISION,
        "task_scope": "bounded repository engineering benchmark",
        "population": "held-out repository tasks",
        "generator_id": "builder-1",
        "generator_family_id": "builder-family",
        "metric_requirements": requirements(),
        "candidate_metrics": {"latency_ms": 90.0, "correctness": 0.90},
        "contamination_status": "clean",
        "contamination_audit_digest": SHA_C,
        "robustness_evidence_digest": SHA_D,
        "security_evidence_digest": SHA_E,
        "efficiency_evidence_digest": "f" * 64,
        "evidence_refs": (
            "benchmark:benchmark-1",
            "dataset:holdout-v1",
            "contamination:audit-1",
            "robustness:matrix-1",
            "security:matrix-1",
            "efficiency:profile-1",
        ),
    }
    values.update(overrides)
    return SOTACandidateClaim(**values)


def replay(subject: SOTACandidateClaim, **overrides) -> SOTAReplayRecord:
    values = {
        "replay_id": "replay-1",
        "claim_digest": subject.digest,
        "source_revision": subject.source_revision,
        "benchmark_digest": subject.benchmark_digest,
        "dataset_digest": subject.dataset_digest,
        "verifier_id": "verifier-1",
        "verifier_family_id": "independent-family",
        "observed_metrics": dict(subject.candidate_metrics),
        "evidence_refs": ("replay:independent-run-1",),
        "passed": True,
    }
    values.update(overrides)
    return SOTAReplayRecord(**values)


def test_exact_independent_replay_qualifies_and_verifies() -> None:
    subject = claim()
    observed = replay(subject)

    receipt = SOTACandidateGate().qualify(subject, observed)
    SOTACandidateGate().verify(subject, observed, receipt)

    assert receipt.status == "qualified_bounded_candidate"
    assert receipt.claim_digest == subject.digest
    assert receipt.replay_digest == observed.digest
    assert receipt.metric_ids == ("correctness", "latency_ms")
    assert len(receipt.qualification_digest) == 64


def test_claim_identity_is_deterministic_across_metric_input_order() -> None:
    first = claim(candidate_metrics={"latency_ms": 90.0, "correctness": 0.90})
    second = claim(candidate_metrics={"correctness": 0.90, "latency_ms": 90.0})

    assert first.digest == second.digest
    assert list(first.candidate_metrics) == ["correctness", "latency_ms"]


def test_claim_metrics_are_defensive_and_immutable() -> None:
    source = {"correctness": 0.90, "latency_ms": 90.0}
    subject = claim(candidate_metrics=source)
    source["correctness"] = 0.1

    assert subject.candidate_metrics["correctness"] == 0.90
    with pytest.raises(TypeError):
        subject.candidate_metrics["correctness"] = 0.2  # type: ignore[index]


def test_unbounded_sota_language_is_rejected() -> None:
    with pytest.raises(SOTACandidateError, match="unbounded"):
        claim(claim_scope="sota")


def test_dirty_or_unknown_contamination_is_rejected() -> None:
    for status in ("unknown", "suspected", "confirmed"):
        with pytest.raises(SOTACandidateError, match="clean contamination"):
            claim(contamination_status=status)


def test_metric_omission_is_rejected() -> None:
    with pytest.raises(SOTACandidateError, match="exactly match"):
        claim(candidate_metrics={"correctness": 0.95})


def test_regression_cannot_be_compensated_by_other_metric() -> None:
    with pytest.raises(SOTACandidateError, match="non-compensable metrics"):
        claim(candidate_metrics={"correctness": 0.99, "latency_ms": 101.0})


def test_candidate_must_strictly_improve_something() -> None:
    flat = (
        SOTAMetricRequirement(
            "correctness",
            SOTAMetricDirection.MAXIMIZE,
            0.80,
            0.0,
        ),
        SOTAMetricRequirement(
            "latency_ms",
            SOTAMetricDirection.MINIMIZE,
            100.0,
            0.0,
        ),
    )
    with pytest.raises(SOTACandidateError, match="strictly improve"):
        claim(
            metric_requirements=flat,
            candidate_metrics={"correctness": 0.80, "latency_ms": 100.0},
        )


def test_nonfinite_metrics_are_rejected() -> None:
    with pytest.raises(SOTACandidateError, match="finite"):
        claim(candidate_metrics={"correctness": math.nan, "latency_ms": 90.0})


def test_claim_requires_multiple_evidence_references() -> None:
    with pytest.raises(SOTACandidateError, match="at least 5"):
        claim(evidence_refs=("benchmark:one",))


def test_self_verification_is_rejected() -> None:
    subject = claim()
    observed = replay(subject, verifier_id=subject.generator_id)

    with pytest.raises(SOTACandidateError, match="self-verify"):
        SOTACandidateGate().qualify(subject, observed)


def test_same_family_verification_is_rejected() -> None:
    subject = claim()
    observed = replay(subject, verifier_family_id=subject.generator_family_id)

    with pytest.raises(SOTACandidateError, match="family"):
        SOTACandidateGate().qualify(subject, observed)


def test_failed_independent_replay_is_rejected() -> None:
    subject = claim()
    observed = replay(subject, passed=False)

    with pytest.raises(SOTACandidateError, match="did not pass"):
        SOTACandidateGate().qualify(subject, observed)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("source_revision", "2" * 40, "source revision"),
        ("benchmark_digest", SHA_C, "benchmark digest"),
        ("dataset_digest", SHA_D, "dataset digest"),
    ),
)
def test_replay_identity_substitution_is_rejected(
    field: str,
    value: str,
    message: str,
) -> None:
    subject = claim()
    observed = replay(subject, **{field: value})

    with pytest.raises(SOTACandidateError, match=message):
        SOTACandidateGate().qualify(subject, observed)


def test_replay_metric_coverage_drift_is_rejected() -> None:
    subject = claim()
    observed = replay(subject, observed_metrics={"correctness": 0.90})

    with pytest.raises(SOTACandidateError, match="coverage"):
        SOTACandidateGate().qualify(subject, observed)


def test_replay_metric_value_drift_is_rejected() -> None:
    subject = claim()
    observed = replay(
        subject,
        observed_metrics={"correctness": 0.91, "latency_ms": 90.0},
    )

    with pytest.raises(SOTACandidateError, match="metrics drift"):
        SOTACandidateGate().qualify(subject, observed)


def test_replay_cannot_be_rebound_to_another_claim() -> None:
    subject = claim()
    other = claim(candidate_id="candidate-2", claim_id="claim-2")
    observed = replay(subject, claim_digest=other.digest)

    with pytest.raises(SOTACandidateError, match="claim identity"):
        SOTACandidateGate().qualify(subject, observed)


def test_qualification_receipt_tampering_is_detected() -> None:
    subject = claim()
    observed = replay(subject)
    receipt = SOTACandidateGate().qualify(subject, observed)
    forged = replace(receipt, qualification_digest="0" * 64)

    with pytest.raises(SOTACandidateError, match="drift|digest"):
        SOTACandidateGate().verify(subject, observed, forged)


def test_claim_scope_constant_remains_bounded() -> None:
    assert SOTA_CANDIDATE_CLAIM == "bounded_sota_candidate"
