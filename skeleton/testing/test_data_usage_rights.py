import pytest
from skeleton.data.usage_rights import *


def test_training_requires_training_grant():
    rights = DataRights(
        "d",
        (UsageGrant("eval", frozenset({"NO"}), 10, False),),
    )
    assert not decide(rights, "eval", "NO", 1, True).allowed


def test_derivative_preserves_rights_lineage():
    assert derive(DataRights("d", ()), "x").lineage == ("d",)


def test_negative_time_denied_and_self_derivation_rejected():
    rights = DataRights(
        "d",
        (UsageGrant("eval", frozenset({"NO"}), 10, False),),
    )
    assert not decide(rights, "eval", "NO", -1).allowed
    with pytest.raises(ValueError):
        derive(rights, "d")


def test_expired_or_wrong_geography_grant_is_denied():
    rights = DataRights(
        "d",
        (UsageGrant("eval", frozenset({"NO"}), 10, True),),
    )
    assert not decide(rights, "eval", "SE", 1).allowed
    assert not decide(rights, "eval", "NO", 11).allowed


def test_lineage_cycles_and_duplicate_lineage_fail_closed():
    with pytest.raises(ValueError):
        DataRights("d", (), ("d",))
    with pytest.raises(ValueError):
        DataRights("d", (), ("a", "a"))


def test_derivative_cannot_reuse_ancestor_identity():
    rights = DataRights("child", (), ("root",))
    with pytest.raises(ValueError):
        derive(rights, "root")
