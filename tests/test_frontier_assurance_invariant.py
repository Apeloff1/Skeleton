import pytest

from skeleton.frontier.assurance.invariant import InvariantViolation, require


def test_require_is_fail_closed():
    require(True, "ok")
    with pytest.raises(InvariantViolation):
        require(False, "blocked")
