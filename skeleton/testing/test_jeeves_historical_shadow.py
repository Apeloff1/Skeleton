from __future__ import annotations

import pytest

from skeleton.jeeves.historical_models import BenchmarkDomain, ModelIdentity
from skeleton.jeeves.historical_shadow import (
    HistoricalShadowError,
    HistoricalShadowLedger,
    ShadowObservation,
    ShadowPolicy,
    make_shadow_provenance,
    summarize_shadow,
)


NOW = 1_000.0
INCUMBENT = ModelIdentity("provider", "incumbent", "r1")
CHALLENGER = ModelIdentity("provider", "challenger", "r2")


def _observation(
    observation_id: str,
    *,
    incumbent_score: float,
    challenger_score: float,
    measured_at: float,
    domain: BenchmarkDomain = BenchmarkDomain.REASONING,
    sample_count: int = 100,
) -> ShadowObservation:
    provenance = make_shadow_provenance(
        source_id=f"shadow:{observation_id}",
        source_kind="benchmark_shadow",
        observation_id=observation_id,
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        domain=domain,
        incumbent_score=incumbent_score,
        challenger_score=challenger_score,
        sample_count=sample_count,
        measured_at=measured_at,
        clock_version=1,
    )
    return ShadowObservation(
        observation_id=observation_id,
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        domain=domain,
        incumbent_score=incumbent_score,
        challenger_score=challenger_score,
        sample_count=sample_count,
        measured_at=measured_at,
        provenance=provenance,
    )


def _passing_ledger():
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    ledger.ingest(_observation("a", incumbent_score=0.80, challenger_score=0.86, measured_at=900.0))
    ledger.ingest(_observation("b", incumbent_score=0.82, challenger_score=0.88, measured_at=910.0))
    ledger.ingest(
        _observation(
            "c",
            incumbent_score=0.84,
            challenger_score=0.89,
            measured_at=920.0,
            domain=BenchmarkDomain.CODING,
        )
    )
    return ledger


def test_paired_shadow_evidence_can_pass_policy() -> None:
    report = _passing_ledger().evaluate(
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        policy=ShadowPolicy(
            min_observations=3,
            min_total_samples=300,
            min_mean_advantage=0.03,
            min_conservative_advantage=0.0,
            max_loss_rate=0.34,
        ),
    )
    assert report.passed
    assert report.observation_count == 3
    assert report.total_samples == 300
    assert report.mean_advantage > 0.0
    assert report.win_rate == 1.0
    assert {item.domain for item in report.domains} == {BenchmarkDomain.REASONING, BenchmarkDomain.CODING}


def test_insufficient_observations_fail_closed() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    ledger.ingest(_observation("a", incumbent_score=0.80, challenger_score=0.90, measured_at=900.0))
    report = ledger.evaluate(
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        policy=ShadowPolicy(min_observations=2, min_total_samples=1, min_mean_advantage=0.0),
    )
    assert not report.passed
    assert "insufficient_observations" in report.reasons


def test_negative_advantage_fails_mean_and_loss_rate() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    for index, measured_at in enumerate((900.0, 910.0, 920.0), start=1):
        ledger.ingest(
            _observation(
                f"loss-{index}",
                incumbent_score=0.90,
                challenger_score=0.80,
                measured_at=measured_at,
            )
        )
    report = ledger.evaluate(
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        policy=ShadowPolicy(
            min_observations=3,
            min_total_samples=1,
            min_mean_advantage=0.0,
            min_conservative_advantage=-1.0,
            max_loss_rate=0.2,
        ),
    )
    assert not report.passed
    assert "insufficient_mean_advantage" in report.reasons
    assert "excessive_loss_rate" in report.reasons


def test_weighted_advantage_respects_sample_count() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    ledger.ingest(_observation("large", incumbent_score=0.80, challenger_score=0.90, measured_at=900.0, sample_count=900))
    ledger.ingest(_observation("small", incumbent_score=0.90, challenger_score=0.80, measured_at=910.0, sample_count=100))
    report = ledger.evaluate(
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        policy=ShadowPolicy(
            min_observations=2,
            min_total_samples=1,
            min_mean_advantage=-1.0,
            min_conservative_advantage=-1.0,
            max_loss_rate=1.0,
            confidence_z=0.0,
        ),
    )
    assert report.mean_advantage == pytest.approx(0.08)


def test_domain_filter_uses_only_requested_paired_evidence() -> None:
    ledger = _passing_ledger()
    report = ledger.evaluate(
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        domains=frozenset({BenchmarkDomain.CODING}),
        policy=ShadowPolicy(
            min_observations=1,
            min_total_samples=1,
            min_mean_advantage=0.0,
            min_conservative_advantage=-1.0,
            max_loss_rate=1.0,
        ),
    )
    assert report.observation_count == 1
    assert report.domains[0].domain is BenchmarkDomain.CODING


def test_stale_evidence_is_excluded() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    ledger.ingest(_observation("old", incumbent_score=0.80, challenger_score=0.90, measured_at=100.0))
    with pytest.raises(HistoricalShadowError):
        ledger.evaluate(
            incumbent=INCUMBENT,
            challenger=CHALLENGER,
            policy=ShadowPolicy(max_age_seconds=100.0),
        )


def test_future_shadow_observation_is_rejected() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    with pytest.raises(HistoricalShadowError):
        ledger.ingest(_observation("future", incumbent_score=0.8, challenger_score=0.9, measured_at=NOW + 1.0))


def test_identical_ingest_is_idempotent() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    observation = _observation("same", incumbent_score=0.8, challenger_score=0.9, measured_at=900.0)
    ledger.ingest(observation)
    ledger.ingest(observation)
    assert len(ledger.observations()) == 1


def test_changed_duplicate_id_is_rejected() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    ledger.ingest(_observation("same", incumbent_score=0.8, challenger_score=0.9, measured_at=900.0))
    with pytest.raises(HistoricalShadowError):
        ledger.ingest(_observation("same", incumbent_score=0.8, challenger_score=0.95, measured_at=910.0))


def test_contradictory_logical_pair_is_rejected() -> None:
    ledger = HistoricalShadowLedger(clock=lambda: NOW)
    ledger.ingest(_observation("a", incumbent_score=0.8, challenger_score=0.9, measured_at=900.0))
    with pytest.raises(HistoricalShadowError):
        ledger.ingest(_observation("b", incumbent_score=0.8, challenger_score=0.95, measured_at=900.0))


def test_provenance_tampering_is_rejected() -> None:
    valid = _observation("a", incumbent_score=0.8, challenger_score=0.9, measured_at=900.0)
    with pytest.raises(HistoricalShadowError):
        ShadowObservation(
            observation_id="tampered",
            incumbent=INCUMBENT,
            challenger=CHALLENGER,
            domain=BenchmarkDomain.REASONING,
            incumbent_score=0.8,
            challenger_score=0.9,
            sample_count=100,
            measured_at=900.0,
            provenance=valid.provenance,
        )


def test_summary_is_json_friendly() -> None:
    report = _passing_ledger().evaluate(
        incumbent=INCUMBENT,
        challenger=CHALLENGER,
        policy=ShadowPolicy(
            min_observations=3,
            min_total_samples=1,
            min_mean_advantage=0.0,
            min_conservative_advantage=-1.0,
            max_loss_rate=1.0,
        ),
    )
    summary = summarize_shadow(report)
    assert summary["challenger"] == CHALLENGER.key
    assert summary["report_fingerprint"] == report.report_fingerprint
    assert len(summary["domains"]) == 2
