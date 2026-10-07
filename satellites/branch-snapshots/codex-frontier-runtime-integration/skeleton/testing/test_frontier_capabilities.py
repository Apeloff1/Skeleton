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


@pytest.mark.parametrize("names", ["text.generate", [1], [None]])
def test_policy_rejects_ambiguous_or_non_string_names(names):
    with pytest.raises(TypeError):
        CapabilityPolicy.from_names(names)


def test_policy_copies_mutable_grants_and_normalizes_requirements():
    grants = {"text.generate"}
    policy = CapabilityPolicy(grants)
    grants.add("code.execute")
    assert policy.permits([" text.generate "])
    assert not policy.permits(["code.execute"])
    with pytest.raises(ValueError):
        policy.require([""])
