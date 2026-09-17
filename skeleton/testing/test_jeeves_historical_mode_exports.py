"""Public-surface smoke tests for Jeeves historical mode laboratories."""

from skeleton.jeeves import (
    BASE_MODES,
    BidirectionalConfig,
    BidirectionalModeLab,
    HistoricalMode,
    HistoricalModeLab,
    HistoricalSeries,
    SelectionGate,
    TemporalDirection,
    WalkForwardConfig,
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
