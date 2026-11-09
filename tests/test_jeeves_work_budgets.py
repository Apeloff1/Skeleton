"""Adversarial work-budget regressions for Jeeves training and evolution."""

import itertools

import pytest

from skeleton.cortex.curriculum import (
    MAX_CURRICULUM_PAIRS,
    MAX_CURRICULUM_TEXT_CHARS,
    MAX_TRAIN_EPOCHS,
    _bounded_curriculum,
    _bounded_epochs,
)
from skeleton.cortex.improve import (
    MAX_IMPROVE_ROUNDS,
    MAX_IMPROVE_STIMULUS_CHARS,
    _bounded_rounds,
    improve,
)


def test_training_epoch_budget_accepts_boundary():
    assert _bounded_epochs(MAX_TRAIN_EPOCHS) == MAX_TRAIN_EPOCHS


def test_training_epoch_budget_rejects_excessive_work():
    with pytest.raises(ValueError, match="safety budget"):
        _bounded_epochs(MAX_TRAIN_EPOCHS + 1)


@pytest.mark.parametrize("value", [True, None, object(), "not-an-int"])
def test_training_epoch_budget_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="integer"):
        _bounded_epochs(value)


def test_curriculum_materialization_is_bounded_for_infinite_iterable():
    infinite = itertools.repeat(("train", "held"))
    with pytest.raises(ValueError, match="safety budget"):
        _bounded_curriculum(infinite)


def test_curriculum_text_size_is_bounded():
    pairs = [("x" * (MAX_CURRICULUM_TEXT_CHARS + 1), "held")]
    with pytest.raises(ValueError, match="text exceeds"):
        _bounded_curriculum(pairs)


def test_curriculum_pair_count_accepts_boundary():
    pairs = [("train", "held")] * MAX_CURRICULUM_PAIRS
    assert len(_bounded_curriculum(pairs)) == MAX_CURRICULUM_PAIRS


def test_curriculum_rejects_malformed_items():
    with pytest.raises(ValueError, match="pairs"):
        _bounded_curriculum([("train",)])
    with pytest.raises(ValueError, match="strings"):
        _bounded_curriculum([(123, "held")])


def test_improve_round_budget_accepts_boundary():
    assert _bounded_rounds(MAX_IMPROVE_ROUNDS) == MAX_IMPROVE_ROUNDS


def test_improve_round_budget_rejects_excessive_work():
    with pytest.raises(ValueError, match="safety budget"):
        _bounded_rounds(MAX_IMPROVE_ROUNDS + 1)


@pytest.mark.parametrize("value", [True, None, object(), "not-an-int"])
def test_improve_round_budget_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="integer"):
        _bounded_rounds(value)


def test_improve_rejects_oversized_stimulus_before_model_work():
    with pytest.raises(ValueError, match="stimulus exceeds"):
        improve(None, "x" * (MAX_IMPROVE_STIMULUS_CHARS + 1), rounds=1)


def test_improve_rejects_excessive_rounds_before_reference_work():
    with pytest.raises(ValueError, match="safety budget"):
        improve(None, "unknown reference", rounds=MAX_IMPROVE_ROUNDS + 1)
