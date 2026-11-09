"""A score that is not a real number in range is not a measurement."""

import pytest

from skeleton.intelligence.calibration import CalibrationError, CalibrationLedger
from skeleton.intelligence.improve_loop import ImproveLoop
from skeleton.intelligence.process_reward import ProcessRewardError, ProcessRewarder


def test_confidence_is_not_clamped_and_an_outcome_must_be_a_bool() -> None:
    ledger = CalibrationLedger(min_samples=2)
    with pytest.raises(CalibrationError):
        ledger.record(5.0, True)
    with pytest.raises(CalibrationError):
        ledger.record(True, True)  # type: ignore[arg-type]
    with pytest.raises(CalibrationError):
        ledger.record(0.9, 1)  # type: ignore[arg-type]
    ledger.record(0.9, False)
    ledger.record(0.9, False)
    assert ledger.correct(0.9) == 0.0


def test_a_step_reward_above_one_cannot_win() -> None:
    rewarder = ProcessRewarder(scorer=lambda step, prev, context: (2.0, 0.0))
    with pytest.raises(ProcessRewardError):
        rewarder.score_trajectory(["look"])
    honest = ProcessRewarder(scorer=lambda step, prev, context: (0.2, 0.2) if step == "short" else (0.8, 0.8))
    index, chosen = honest.select_best([["short"], ["long"]])
    assert index == 1
    assert chosen.steps == ["long"]


def test_an_improvement_score_must_be_finite() -> None:
    loop = ImproveLoop(max_iterations=1, patience=1)
    with pytest.raises(ValueError):
        loop.run(1, lambda incumbent, i: incumbent, lambda value: float("nan"))
    with pytest.raises(ValueError):
        ImproveLoop(target=float("nan"))
