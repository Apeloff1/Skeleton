import pytest

from skeleton.frontier.assurance.verification import Verification


def test_verification_is_explicitly_enforced():
    Verification("artifact", True, ("unit",)).require()
    with pytest.raises(RuntimeError):
        Verification("artifact", False, ("unit",)).require()
