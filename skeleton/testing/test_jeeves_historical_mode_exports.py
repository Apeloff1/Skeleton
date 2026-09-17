"""Public-surface smoke tests for Jeeves historical mode laboratories."""

from skeleton.jeeves import (
    BASE_MODES,
    BidirectionalConfig,
    BidirectionalModeLab,
    CalibratedBidirectionalModeLab,
    CrossDirectionConfig,
    HistoricalEvidenceBundle,
    HistoricalMode,
    HistoricalModeLab,
    HistoricalSeries,
    SelectionGate,
    TemporalDirection,
    TemporalJackknifeConfig,
    TemporalJackknifeModeLab,
    TemporalViewKind,
    WalkForwardConfig,
    build_historical_evidence,
    bundle_manifest,
    reverse_series,
)


def test_historical_mode_lab_is_available_from_public_jeeves_surface() -> None:
    assert HistoricalMode.PERSISTENCE in BASE_MODES
    lab = HistoricalModeLab(
        config=WalkForwardConfig(min_train_size=4),
        gate=SelectionGate(min_folds=2, min_relative_improvement=0.0),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    report = lab.evaluate(HistoricalSeries.from_values([1, 2, 3, 4, 5, 6, 7]))
    assert report.by_mode(HistoricalMode.PERSISTENCE).metrics.folds == 3
    assert report.by_mode(HistoricalMode.LINEAR_TREND).metrics.folds == 3


def test_bidirectional_mode_lab_is_available_from_public_jeeves_surface() -> None:
    lab = BidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=4),
        gate=SelectionGate(min_folds=2, min_relative_improvement=0.0),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=1.0, max_direction_rank=2),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    series = HistoricalSeries.from_values([1, 2, 3, 4, 5, 6, 7, 8])
    report = lab.evaluate(series)
    assert report.forward.direction is TemporalDirection.FORWARD
    assert report.backward.direction is TemporalDirection.BACKWARD
    assert reverse_series(series).values == tuple(reversed(series.values))


def test_calibrated_bidirectional_lab_is_available_from_public_surface() -> None:
    lab = CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=4),
        gate=SelectionGate(min_folds=2, min_relative_improvement=0.0),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=1.0, max_direction_rank=2),
        calibration=CrossDirectionConfig(
            top_k=2,
            min_rank_correlation=-1.0,
            min_top_k_overlap=0.0,
            max_candidate_rank_gap=2,
            min_paired_targets=0,
        ),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    report = lab.evaluate(HistoricalSeries.from_values(range(1, 13)))
    assert report.ranking_agreement.common_modes >= 2
    assert report.decision.candidate is report.base.decision.candidate
    assert report.by_mode(HistoricalMode.PERSISTENCE).mode is HistoricalMode.PERSISTENCE


def test_temporal_jackknife_lab_is_available_from_public_surface() -> None:
    lab = TemporalJackknifeModeLab(
        config=WalkForwardConfig(min_train_size=4),
        gate=SelectionGate(min_folds=2, min_relative_improvement=0.0),
        jackknife=TemporalJackknifeConfig(
            trim_fraction=0.10,
            max_trim=2,
            min_views=2,
            min_acceptance_rate=0.0,
            min_candidate_support_rate=0.0,
            max_candidate_mae_spread=100.0,
        ),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    report = lab.evaluate(HistoricalSeries.from_values(range(1, 21)))
    assert report.by_view(TemporalViewKind.FULL).start == 0
    assert report.decision.total_views >= 2


def test_historical_evidence_bridge_is_available_from_public_surface() -> None:
    series = HistoricalSeries.from_values(range(1, 17), label="public-evidence")
    lab = CalibratedBidirectionalModeLab(
        config=WalkForwardConfig(min_train_size=4),
        gate=SelectionGate(min_folds=2, min_relative_improvement=0.0),
        bidirectional=BidirectionalConfig(max_mae_asymmetry=1.0, max_direction_rank=2),
        calibration=CrossDirectionConfig(
            top_k=2,
            min_rank_correlation=-1.0,
            min_top_k_overlap=0.0,
            max_candidate_rank_gap=2,
            min_paired_targets=0,
        ),
        modes=(HistoricalMode.LINEAR_TREND,),
    )
    report = lab.evaluate(series)
    bundle = build_historical_evidence(report, series, subject_id="public-evidence")
    assert isinstance(bundle, HistoricalEvidenceBundle)
    assert bundle.features
    assert "report_fingerprint" in bundle_manifest(bundle)
