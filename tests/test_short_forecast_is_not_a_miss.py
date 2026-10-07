"""Too little history is not a forecast that the threshold will not be crossed."""

import pytest

from skeleton.intelligence.forecaster import Forecaster


def test_short_history_does_not_report_no_crossing() -> None:
    caster = Forecaster()
    caster.feed("queue", 1.0)
    with pytest.raises(ValueError):
        caster.forecast("queue")
    with pytest.raises(ValueError):
        caster.time_to_threshold("queue", 10.0)
    with pytest.raises(ValueError):
        caster.anomalies_foreseen("queue")
    with pytest.raises(ValueError):
        caster.anomalies_foreseen("queue", zscore=True)
    for value in (1.0, 2.0, 3.0):
        caster.feed("ready", value)
    assert caster.forecast("ready", steps=1)["samples"] == 3
