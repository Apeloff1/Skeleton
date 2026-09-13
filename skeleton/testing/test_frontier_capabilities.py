import pytest

from skeleton.frontier.capabilities import CapabilityPolicy


def test_policy_normalizes_and_permits():
    policy = CapabilityPolicy.from_names([" memory.read ", "world.write", ""])
    assert policy.permits(["memory.read"])
    assert policy.permits(["memory.read", "world.write"])


def test_policy_rejects_missing_capabilities():
    policy = CapabilityPolicy.from_names(["memory.read"])
    with pytest.raises(PermissionError, match="world.write"):
        policy.require(["memory.read", "world.write"])
