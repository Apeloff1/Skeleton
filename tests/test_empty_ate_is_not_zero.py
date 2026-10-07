"""No observations is not an effect of zero with no error."""

import pytest

from skeleton.intelligence.causal import CausalInference


def test_missing_observations_do_not_estimate_zero() -> None:
    empty = CausalInference()
    with pytest.raises(ValueError):
        empty.estimate_ate("treated", "outcome")
    flagged = CausalInference()
    flagged.add_observation({"treated": True, "outcome": 1})
    flagged.add_observation({"treated": 0, "outcome": 0})
    with pytest.raises(ValueError):
        flagged.estimate_ate("treated", "outcome")
    engine = CausalInference()
    engine.add_observation({"treated": 1, "outcome": 3})
    engine.add_observation({"treated": 0, "outcome": 1})
    ate, _error = engine.estimate_ate("treated", "outcome")
    assert ate == 2.0
    engine.add_observation({"treated": 1})
    with pytest.raises(ValueError):
        engine.estimate_ate("treated", "outcome")
