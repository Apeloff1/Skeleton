"""No history is not a measured rate of zero, and a blank query is not easy."""

import pytest

from skeleton.forge.sim import EncounterResult
from skeleton.intelligence.calibration import CalibrationLedger
from skeleton.intelligence.cascade import difficulty_estimate
from skeleton.intelligence.process_reward import heuristic_step_scorer
from skeleton.intelligence.verifier import CodeVerifier


def test_empty_history_does_not_look_measured() -> None:
    assert CalibrationLedger().expected_calibration_error() is None
    assert CalibrationLedger().stats()["ece"] is None
    assert CodeVerifier(accept_at=0.7).stats()["accept_rate"] is None
    with pytest.raises(ValueError):
        difficulty_estimate("  ")
    _, alignment = heuristic_step_scorer("open the gate", None, {})
    assert alignment == 0.0
    with pytest.raises(ValueError):
        _ = EncounterResult("e", "ideal", 0, 1, 1, 0, False, False, False).error
