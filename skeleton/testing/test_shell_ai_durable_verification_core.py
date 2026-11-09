"""Focused bounds and fail-closed tests for durable verification operations."""

import pytest

from skeleton.shells.ai.durable_verification_health import (
    DurableVerificationFleetPolicy,
)
from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperator,
    DurableVerificationOperatorPolicy,
)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_fleet_policy_rejects_invalid_max_chains(value):
    with pytest.raises(ValueError, match="max_chains"):
        DurableVerificationFleetPolicy(max_chains=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_fleet_policy_rejects_invalid_max_findings(value):
    with pytest.raises(ValueError, match="max_findings"):
        DurableVerificationFleetPolicy(max_findings=value)


@pytest.mark.parametrize("field", [
    "require_cursor_current",
    "tail_pending_is_warning",
    "full_required_is_warning",
])
def test_fleet_policy_requires_boolean_flags(field):
    kwargs = {field: 1}
    with pytest.raises(ValueError, match=field):
        DurableVerificationFleetPolicy(**kwargs)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_operator_policy_rejects_invalid_max_chains(value):
    with pytest.raises(ValueError, match="max_chains"):
        DurableVerificationOperatorPolicy(max_chains=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_operator_policy_rejects_invalid_lineage_bound(value):
    with pytest.raises(ValueError, match="max_lineage_items"):
        DurableVerificationOperatorPolicy(max_lineage_items=value)


def test_verification_policy_digests_are_stable_sha256():
    fleet = DurableVerificationFleetPolicy()
    operator = DurableVerificationOperatorPolicy()
    assert len(fleet.digest) == 64
    assert fleet.digest == DurableVerificationFleetPolicy().digest
    assert len(operator.digest) == 64
    assert operator.digest == DurableVerificationOperatorPolicy().digest


def test_operator_rejects_untyped_store_before_runtime_use():
    with pytest.raises(TypeError, match="store must be DurableVerificationCursorStore"):
        DurableVerificationOperator(object(), object())
