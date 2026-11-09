from __future__ import annotations

import pytest

from skeleton.jeeves.historical_assurance import HistoricalAssuranceReport
from skeleton.jeeves.historical_comparability import BenchmarkComparabilityReport
from skeleton.jeeves.historical_independence import EvidenceIndependenceReport
from skeleton.jeeves.historical_models import ModelIdentity
from skeleton.jeeves.historical_readiness import (
    HistoricalReadinessError,
    HistoricalReadinessGate,
    HistoricalReadinessReport,
    ReadinessCheck,
    ReadinessEvidence,
    ReadinessPolicy,
    summarize_readiness,
)
from skeleton.jeeves.historical_shadow import ShadowEvaluationReport


CANDIDATE = ModelIdentity("provider", "candidate", "r1")
OTHER = ModelIdentity("provider", "other", "r1")
INCUMBENT = ModelIdentity("provider", "incumbent", "r0")


def _assurance(*, passed=True, candidate=CANDIDATE):
    return HistoricalAssuranceReport(
        candidate=candidate,
        passed=passed,
        checks=(),
        reasons=() if passed else ("fixture_failure",),
        policy_fingerprint="assurance-policy",
        backtest_fingerprint="backtest",
        calibration_fingerprint="calibration",
        sensitivity_fingerprint="sensitivity",
        drift_fingerprint=None,
        report_fingerprint="assurance-report",
    )


def _independence(*, passed=True, candidate=CANDIDATE):
    return EvidenceIndependenceReport(
        champion_model=candidate.key,
        used_snapshot_ids=("s1", "s2"),
        declared_snapshot_count=2,
        undeclared_snapshot_ids=(),
        used_cohort_ids=("c1", "c2"),
        independent_population_count=2,
        max_observed_overlap=0.0,
        findings=(),
        passed=passed,
        policy_fingerprint="independence-policy",
        declaration_fingerprint="declarations",
        report_fingerprint="independence-report",
    )


def _comparability(*, passed=True, candidate=CANDIDATE):
    return BenchmarkComparabilityReport(
        champion_model=candidate.key,
        domains=(),
        incompatible_domains=(),
        passed=passed,
        contract_set_fingerprint="contracts",
        report_fingerprint="comparability-report",
    )


def _shadow(*, passed=True, challenger=CANDIDATE):
    return ShadowEvaluationReport(
        incumbent=INCUMBENT,
        challenger=challenger,
        observation_count=3,
        total_samples=300,
        mean_advantage=0.05,
        conservative_advantage=0.02,
        win_rate=1.0,
        loss_rate=0.0,
        domains=(),
        reasons=() if passed else ("insufficient_conservative_advantage",),
        passed=passed,
        policy_fingerprint="shadow-policy",
        evidence_fingerprint="shadow-evidence",
        report_fingerprint="shadow-report",
    )


def _evidence(*, assurance=True, independence=True, comparability=True, shadow=None):
    return ReadinessEvidence(
        candidate=CANDIDATE,
        assurance=_assurance(passed=assurance),
        independence=_independence(passed=independence),
        comparability=_comparability(passed=comparability),
        shadow=shadow,
    )


def test_all_required_planes_must_pass() -> None:
    report = HistoricalReadinessGate().evaluate(_evidence())
    assert report.passed
    assert report.failed_count == 0
    assert report.reasons == ()


@pytest.mark.parametrize(
    ("plane", "expected_reason"),
    [
        ("assurance", "failed:assurance"),
        ("independence", "failed:independence"),
        ("comparability", "failed:comparability"),
    ],
)
def test_single_plane_failure_blocks_readiness(plane, expected_reason) -> None:
    kwargs = {"assurance": True, "independence": True, "comparability": True}
    kwargs[plane] = False
    report = HistoricalReadinessGate().evaluate(_evidence(**kwargs))
    assert not report.passed
    assert expected_reason in report.reasons
    assert report.failed_count == 1


def test_missing_required_plane_fails_closed() -> None:
    evidence = ReadinessEvidence(
        candidate=CANDIDATE,
        assurance=_assurance(),
        independence=None,
        comparability=_comparability(),
    )
    report = HistoricalReadinessGate().evaluate(evidence)
    assert not report.passed
    assert "missing:independence" in report.reasons


def test_optional_plane_can_be_absent() -> None:
    policy = ReadinessPolicy(
        require_assurance=True,
        require_independence=False,
        require_comparability=True,
    )
    evidence = ReadinessEvidence(
        candidate=CANDIDATE,
        assurance=_assurance(),
        independence=None,
        comparability=_comparability(),
    )
    report = HistoricalReadinessGate(policy).evaluate(evidence)
    assert report.passed
    by_id = {item.check_id: item for item in report.checks}
    assert not by_id["independence"].required
    assert not by_id["independence"].present
    assert not by_id["shadow"].required
    assert not by_id["shadow"].present


def test_required_shadow_must_be_present() -> None:
    report = HistoricalReadinessGate(ReadinessPolicy(require_shadow=True)).evaluate(_evidence())
    assert not report.passed
    assert "missing:shadow" in report.reasons


def test_required_shadow_must_pass() -> None:
    report = HistoricalReadinessGate(ReadinessPolicy(require_shadow=True)).evaluate(
        _evidence(shadow=_shadow(passed=False))
    )
    assert not report.passed
    assert "failed:shadow" in report.reasons


def test_required_passing_shadow_allows_readiness() -> None:
    report = HistoricalReadinessGate(ReadinessPolicy(require_shadow=True)).evaluate(
        _evidence(shadow=_shadow())
    )
    assert report.passed
    by_id = {item.check_id: item for item in report.checks}
    assert by_id["shadow"].required
    assert by_id["shadow"].passed
    assert by_id["shadow"].evidence_fingerprint == "shadow-report"


def test_shadow_challenger_mismatch_rejected() -> None:
    with pytest.raises(HistoricalReadinessError):
        _evidence(shadow=_shadow(challenger=OTHER))


def test_policy_cannot_disable_every_evidence_plane() -> None:
    with pytest.raises(HistoricalReadinessError):
        ReadinessPolicy(
            require_assurance=False,
            require_independence=False,
            require_comparability=False,
            require_shadow=False,
        )


@pytest.mark.parametrize(
    "evidence",
    [
        ReadinessEvidence(
            candidate=CANDIDATE,
            assurance=_assurance(),
            independence=_independence(),
            comparability=_comparability(),
        ),
    ],
)
def test_report_fingerprint_is_deterministic(evidence) -> None:
    gate = HistoricalReadinessGate()
    assert gate.evaluate(evidence).report_fingerprint == gate.evaluate(evidence).report_fingerprint


def test_assurance_candidate_mismatch_rejected() -> None:
    with pytest.raises(HistoricalReadinessError):
        ReadinessEvidence(
            candidate=CANDIDATE,
            assurance=_assurance(candidate=OTHER),
            independence=_independence(),
            comparability=_comparability(),
        )


def test_independence_candidate_mismatch_rejected() -> None:
    with pytest.raises(HistoricalReadinessError):
        ReadinessEvidence(
            candidate=CANDIDATE,
            assurance=_assurance(),
            independence=_independence(candidate=OTHER),
            comparability=_comparability(),
        )


def test_comparability_candidate_mismatch_rejected() -> None:
    with pytest.raises(HistoricalReadinessError):
        ReadinessEvidence(
            candidate=CANDIDATE,
            assurance=_assurance(),
            independence=_independence(),
            comparability=_comparability(candidate=OTHER),
        )


def test_forged_readiness_pass_state_is_rejected() -> None:
    failed = ReadinessCheck(
        check_id="assurance",
        required=True,
        present=True,
        passed=False,
        evidence_fingerprint="evidence",
    )
    with pytest.raises(HistoricalReadinessError):
        HistoricalReadinessReport(
            candidate=CANDIDATE,
            passed=True,
            checks=(failed,),
            reasons=("failed:assurance",),
            policy_fingerprint="policy",
            report_fingerprint="forged",
        )


def test_forged_readiness_reasons_are_rejected() -> None:
    missing = ReadinessCheck(
        check_id="independence",
        required=True,
        present=False,
        passed=False,
        evidence_fingerprint=None,
    )
    with pytest.raises(HistoricalReadinessError):
        HistoricalReadinessReport(
            candidate=CANDIDATE,
            passed=False,
            checks=(missing,),
            reasons=("failed:independence",),
            policy_fingerprint="policy",
            report_fingerprint="forged",
        )


def test_forged_readiness_fingerprint_is_rejected() -> None:
    passing = ReadinessCheck(
        check_id="assurance",
        required=True,
        present=True,
        passed=True,
        evidence_fingerprint="evidence",
    )
    with pytest.raises(HistoricalReadinessError):
        HistoricalReadinessReport(
            candidate=CANDIDATE,
            passed=True,
            checks=(passing,),
            reasons=(),
            policy_fingerprint="policy",
            report_fingerprint="forged",
        )


def test_summary_exposes_required_evidence_fingerprints() -> None:
    report = HistoricalReadinessGate(ReadinessPolicy(require_shadow=True)).evaluate(
        _evidence(shadow=_shadow())
    )
    summary = summarize_readiness(report)
    assert summary["passed"] is True
    assert summary["report_fingerprint"] == report.report_fingerprint
    checks = {item["check_id"]: item for item in summary["checks"]}
    assert checks["assurance"]["evidence_fingerprint"] == "assurance-report"
    assert checks["independence"]["evidence_fingerprint"] == "independence-report"
    assert checks["comparability"]["evidence_fingerprint"] == "comparability-report"
    assert checks["shadow"]["evidence_fingerprint"] == "shadow-report"
