"""Regression tests for leakage-safe Dragon empirical calibration."""
import pytest
from skeleton.ai.webcrawler.dragon_empirical_calibration import (
    apply_calibrator, fit_histogram_calibrator,
)
from skeleton.ai.webcrawler.dragon_probability_calibration import CalibrationExample


def dataset():
    rows = []
    for period in ("train-a", "train-b", "holdout"):
        for index in range(100):
            p = (index + .5) / 100
            rows.append(CalibrationExample(
                f"{period}-{index}", p, p >= .5,
                f"group-{index % 5}", period,
            ))
    return tuple(rows)


def test_period_overlap_is_rejected():
    with pytest.raises(ValueError, match="leakage"):
        fit_histogram_calibrator(
            dataset(), training_periods=("train-a",),
            evaluation_periods=("train-a",), authorized=True,
        )


def test_fit_is_deterministic():
    kwargs = dict(
        training_periods=("train-a", "train-b"),
        evaluation_periods=("holdout",),
        authorized=True, bins=4, minimum_bin_samples=20,
    )
    assert fit_histogram_calibrator(dataset(), **kwargs) == fit_histogram_calibrator(
        dataset(), **kwargs,
    )


def test_heldout_period_never_enters_training_count():
    artifact = fit_histogram_calibrator(
        dataset(), training_periods=("train-a", "train-b"),
        evaluation_periods=("holdout",), authorized=True,
        bins=4, minimum_bin_samples=20,
    )
    assert artifact.training_samples == 200
    assert artifact.evaluation.samples == 100


def test_sparse_calibrator_cannot_be_applied():
    artifact = fit_histogram_calibrator(
        dataset(), training_periods=("train-a",),
        evaluation_periods=("holdout",), authorized=True,
        bins=50, minimum_bin_samples=10,
    )
    assert not artifact.eligible
    with pytest.raises(ValueError, match="not eligible"):
        apply_calibrator(.7, artifact)


def test_eligible_calibrator_maps_score_to_empirical_rate():
    artifact = fit_histogram_calibrator(
        dataset(), training_periods=("train-a", "train-b"),
        evaluation_periods=("holdout",), authorized=True,
        bins=4, minimum_bin_samples=20,
    )
    assert artifact.eligible
    assert 0 <= apply_calibrator(.8, artifact) <= 1


def test_authorization_required():
    with pytest.raises(PermissionError):
        fit_histogram_calibrator(
            dataset(), training_periods=("train-a",),
            evaluation_periods=("holdout",), authorized=False,
        )
