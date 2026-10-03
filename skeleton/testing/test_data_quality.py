import math

import pytest

from skeleton.data.quality import (
    DataQualityEngine,
    DataQualityError,
    DataQualityRule,
    QualityObservation,
)


def test_critical_failure_and_missing_observation_block() -> None:
    engine = DataQualityEngine(
        [DataQualityRule("coverage", "coverage", "gte", 1.0, True)]
    )
    observed = engine.evaluate(
        dataset_id="dataset",
        version=1,
        observations=[QualityObservation("coverage", 0.9, 10)],
    )
    missing = engine.evaluate(
        dataset_id="dataset",
        version=1,
        observations=[],
    )
    assert observed.promotion_allowed is False
    assert observed.observations[0].value == 0.9
    assert missing.promotion_allowed is False


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_nonfinite_or_boolean_observation_fails(value) -> None:
    engine = DataQualityEngine(
        [DataQualityRule("coverage", "coverage", "gte", 0.5, True)]
    )
    with pytest.raises(DataQualityError, match="invalid observations"):
        engine.evaluate(
            dataset_id="dataset",
            version=1,
            observations=[QualityObservation("coverage", value, 1)],
        )


def test_nonfinite_rule_threshold_fails() -> None:
    with pytest.raises(DataQualityError, match="invalid rule"):
        DataQualityEngine(
            [DataQualityRule("coverage", "coverage", "gte", math.nan, True)]
        )
