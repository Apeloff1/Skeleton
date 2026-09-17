"""Public-surface smoke test for the Jeeves historical mode laboratory."""

from skeleton.jeeves import (
    BASE_MODES,
    HistoricalMode,
    HistoricalModeLab,
    HistoricalSeries,
    SelectionGate,
    WalkForwardConfig,
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
