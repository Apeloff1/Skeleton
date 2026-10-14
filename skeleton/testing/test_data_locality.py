import pytest
from skeleton.data.locality import *


def test_locality_never_overrides_security_region():
    assert not plan_transfer(
        DataLocation("a", 1, "secret"),
        "b",
        LocalityConstraint(frozenset({"a"}), 5),
        1,
    ).allowed


def test_stale_local_copy_not_preferred():
    assert not plan_transfer(
        DataLocation("a", 10, "x"),
        "a",
        LocalityConstraint(frozenset({"a"}), 5),
        0,
    ).allowed


def test_region_allowed_but_classification_denied():
    source = DataLocation("NO", 0, "secret")
    constraint = LocalityConstraint(
        frozenset({"NO"}),
        10,
        frozenset({"public"}),
    )
    assert not plan_transfer(source, "NO", constraint, 1).allowed


def test_source_and_target_must_both_satisfy_residency():
    source = DataLocation("US", 0, "public")
    constraint = LocalityConstraint(frozenset({"NO"}), 10)
    assert not plan_transfer(source, "NO", constraint, 1).allowed


def test_valid_transfer_normalizes_numeric_cost():
    source = DataLocation("NO", 0, "public")
    constraint = LocalityConstraint(frozenset({"NO", "SE"}), 10)
    plan = plan_transfer(source, "SE", constraint, 2, )
    assert plan.allowed and plan.cost == 2.0


def test_empty_policy_and_boolean_age_fail_closed():
    with pytest.raises(ValueError):
        LocalityConstraint(frozenset(), 10)
    with pytest.raises(ValueError):
        DataLocation("NO", True, "public")
