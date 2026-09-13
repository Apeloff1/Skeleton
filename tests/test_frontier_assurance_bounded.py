import pytest

from skeleton.frontier.assurance.bounded import BoundedInt


def test_bounded_value_and_clamp():
    value = BoundedInt(5, 0, 10)
    assert value.clamp(99).value == 10
    assert value.clamp(-1).value == 0
    with pytest.raises(ValueError):
        BoundedInt(11, 0, 10)
