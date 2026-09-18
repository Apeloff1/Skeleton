from __future__ import annotations

import pytest

from skeleton.jeeves.historical_comparability import (
    BenchmarkCompatibilityContract,
    HistoricalBenchmarkComparabilityAuditor,
    HistoricalComparabilityError,
    summarize_comparability,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    canonical_fingerprint,
    make_benchmark_provenance,
)


NOW = 1_000.0
REASON_V1 = BenchmarkDefinition("reason-suite", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
REASON_V2 = BenchmarkDefinition("reason-suite", "v2", BenchmarkDomain.REASONING, 0.0, 120.0)
ALT_REASON = BenchmarkDefinition("other-reason", "v1", BenchmarkDomain.REASONING, 0.0, 1.0)
CODE = BenchmarkDefinition("code-suite", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
MODEL = ModelIdentity("provider", "candidate", "r1")


def _snapshot(snapshot_id, benchmark, raw_score, measured_at):
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=MODEL,
        benchmark=benchmark,
        raw_score=raw_score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=MODEL,
        benchmark=benchmark,
        raw_score=raw_score,
        sample_count=100,
        measured_at=measured_at,
        provenance=provenance,
    )


def _decision(*snapshots):
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    for snapshot in snapshots:
        registry.ingest(snapshot)
    domains = {snapshot.benchmark.domain for snapshot in snapshots}
    decision = registry.select_champion(
        SelectionPolicy(
            domain_weights={domain: 1.0 for domain in domains},
            required_domains=frozenset(domains),
            minimum_sample_count=1,
            confidence_z=0.0,
        )
    )
    return registry, decision


def _contract(*keys, contract_id="reason-compatible", revision="v1"):
    return BenchmarkCompatibilityContract(
        contract_id=contract_id,
        revision=revision,
        domain=BenchmarkDomain.REASONING,
        benchmark_keys=frozenset(keys),
        rationale_fingerprint=canonical_fingerprint({"keys": sorted(keys), "basis": "fixture"}),
    )


def test_single_benchmark_domain_needs_no_contract() -> None:
    registry, decision = _decision(_snapshot("r1", REASON_V1, 90.0, 800.0))
    report = HistoricalBenchmarkComparabilityAuditor().audit(decision=decision, registry=registry)
    assert report.passed
    assert report.domains[0].reason == "single_benchmark"


def test_multiple_revisions_same_domain_fail_without_contract() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
    )
    report = HistoricalBenchmarkComparabilityAuditor().audit(decision=decision, registry=registry)
    assert not report.passed
    assert report.incompatible_domains == (BenchmarkDomain.REASONING,)
    assert report.domains[0].reason == "missing_contract"


def test_explicit_contract_allows_revision_blend() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
    )
    contract = _contract(REASON_V1.key, REASON_V2.key)
    report = HistoricalBenchmarkComparabilityAuditor([contract]).audit(decision=decision, registry=registry)
    assert report.passed
    assert report.domains[0].contract_key == contract.key
    assert report.domains[0].contract_fingerprint == contract.fingerprint


def test_contract_must_cover_every_used_benchmark_key() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
        _snapshot("r3", ALT_REASON, 0.92, 880.0),
    )
    contract = _contract(REASON_V1.key, REASON_V2.key)
    report = HistoricalBenchmarkComparabilityAuditor([contract]).audit(decision=decision, registry=registry)
    assert not report.passed
    assert report.domains[0].reason == "missing_contract"


def test_ambiguous_compatible_contracts_fail_closed() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
    )
    contracts = [
        _contract(REASON_V1.key, REASON_V2.key, contract_id="a"),
        _contract(REASON_V1.key, REASON_V2.key, contract_id="b"),
    ]
    report = HistoricalBenchmarkComparabilityAuditor(contracts).audit(decision=decision, registry=registry)
    assert not report.passed
    assert report.domains[0].reason == "ambiguous_contract"


def test_wrong_domain_contract_cannot_authorize_blend() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
    )
    wrong = BenchmarkCompatibilityContract(
        contract_id="wrong",
        revision="v1",
        domain=BenchmarkDomain.CODING,
        benchmark_keys=frozenset({REASON_V1.key, REASON_V2.key}),
        rationale_fingerprint="fixture-rationale",
    )
    report = HistoricalBenchmarkComparabilityAuditor([wrong]).audit(decision=decision, registry=registry)
    assert not report.passed


def test_multi_domain_audit_only_requires_contract_for_blended_domain() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
        _snapshot("c1", CODE, 91.0, 870.0),
    )
    report = HistoricalBenchmarkComparabilityAuditor([
        _contract(REASON_V1.key, REASON_V2.key)
    ]).audit(decision=decision, registry=registry)
    assert report.passed
    by_domain = {item.domain: item for item in report.domains}
    assert by_domain[BenchmarkDomain.REASONING].reason == "explicit_contract"
    assert by_domain[BenchmarkDomain.CODING].reason == "single_benchmark"


def test_audit_rejects_decision_snapshot_absent_from_registry() -> None:
    source_registry, decision = _decision(_snapshot("r1", REASON_V1, 90.0, 800.0))
    assert source_registry.snapshots()
    empty_registry = HistoricalModelRegistry(clock=lambda: NOW)
    with pytest.raises(HistoricalComparabilityError):
        HistoricalBenchmarkComparabilityAuditor().audit(decision=decision, registry=empty_registry)


def test_contract_key_must_be_unique() -> None:
    contract = _contract(REASON_V1.key, REASON_V2.key)
    with pytest.raises(HistoricalComparabilityError):
        HistoricalBenchmarkComparabilityAuditor([contract, contract])


def test_contract_requires_at_least_two_benchmarks() -> None:
    with pytest.raises(HistoricalComparabilityError):
        _contract(REASON_V1.key)


def test_contract_set_fingerprint_is_order_independent() -> None:
    first = _contract(REASON_V1.key, REASON_V2.key, contract_id="a")
    second = _contract(REASON_V1.key, ALT_REASON.key, contract_id="b")
    left = HistoricalBenchmarkComparabilityAuditor([first, second])
    right = HistoricalBenchmarkComparabilityAuditor([second, first])
    assert left.contract_set_fingerprint == right.contract_set_fingerprint


def test_summary_is_json_friendly() -> None:
    registry, decision = _decision(
        _snapshot("r1", REASON_V1, 90.0, 800.0),
        _snapshot("r2", REASON_V2, 108.0, 850.0),
    )
    report = HistoricalBenchmarkComparabilityAuditor([
        _contract(REASON_V1.key, REASON_V2.key)
    ]).audit(decision=decision, registry=registry)
    summary = summarize_comparability(report)
    assert summary["passed"] is True
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert summary["domains"][0]["compatible"] is True