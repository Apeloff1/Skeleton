import pytest

from skeleton.frontier.assurance.result import Outcome


def test_outcome_is_exclusive():
    assert Outcome(value=7).ok
    assert not Outcome(error="blocked").ok
    with pytest.raises(ValueError):
        Outcome(value=7, error="blocked")
