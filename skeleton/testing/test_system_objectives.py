from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.objectives import (
    Objective,
    ObjectiveCriterion,
    ObjectiveOrigin,
    ObjectiveRecord,
    ObjectiveState,
)
from skeleton.contracts.canonical import canonical_json_bytes


def criterion(name: str = "done") -> ObjectiveCriterion:
    return ObjectiveCriterion(name, f"{name} is independently observable")


def test_requested_and_inferred_objectives_remain_distinct() -> None:
    root = Objective("Build safe system", ObjectiveOrigin.REQUESTED, (criterion(),), constraints=("policy",))
    child = root.infer("Run bounded validation", (criterion("validated"),))
    assert root.origin is ObjectiveOrigin.REQUESTED
    assert root.parent_id is None
    assert child.origin is ObjectiveOrigin.INFERRED
    assert child.parent_id == root.identity


def test_identity_uses_shared_canonical_bytes() -> None:
    obj = Objective("Build safe system", ObjectiveOrigin.REQUESTED, (criterion(),))
    assert obj.identity == hashlib.sha256(canonical_json_bytes(obj.canonical_payload())).hexdigest()


@pytest.mark.parametrize("policy,authority", [(False, True), (True, False), (False, False)])
def test_objective_cannot_override_policy_or_authority(policy: bool, authority: bool) -> None:
    record = ObjectiveRecord(Objective("Do work", ObjectiveOrigin.REQUESTED, (criterion(),)))
    blocked = record.activate(policy_allowed=policy, authority_allowed=authority)
    assert blocked.state is ObjectiveState.BLOCKED


def test_authorized_objective_lifecycle_requires_all_criteria() -> None:
    obj = Objective("Ship", ObjectiveOrigin.REQUESTED, (criterion("tested"), criterion("reviewed")))
    active = ObjectiveRecord(obj).activate(policy_allowed=True, authority_allowed=True)
    assert active.state is ObjectiveState.ACTIVE
    partial = active.mark_satisfied("tested")
    assert partial.state is ObjectiveState.ACTIVE
    complete = partial.mark_satisfied("reviewed")
    assert complete.state is ObjectiveState.SATISFIED


def test_inferred_goal_requires_parent_and_requested_goal_cannot_claim_parent() -> None:
    with pytest.raises(ValueError):
        Objective("Subgoal", ObjectiveOrigin.INFERRED, (criterion(),))
    with pytest.raises(ValueError):
        Objective("Root", ObjectiveOrigin.REQUESTED, (criterion(),), parent_id="forged")


def test_satisfied_state_cannot_be_fabricated() -> None:
    obj = Objective("Ship", ObjectiveOrigin.REQUESTED, (criterion("a"), criterion("b")))
    with pytest.raises(ValueError):
        ObjectiveRecord(obj, ObjectiveState.SATISFIED, ("a",))


def test_unknown_or_duplicate_criteria_fail_closed() -> None:
    obj = Objective("Ship", ObjectiveOrigin.REQUESTED, (criterion("a"),))
    active = ObjectiveRecord(obj).activate(policy_allowed=True, authority_allowed=True)
    with pytest.raises(ValueError):
        active.mark_satisfied("invented")
    with pytest.raises(ValueError):
        Objective("Bad", ObjectiveOrigin.REQUESTED, (criterion("a"), criterion("a")))


def test_constraints_are_explicit_and_unique() -> None:
    with pytest.raises(ValueError):
        Objective("Bad", ObjectiveOrigin.REQUESTED, (criterion(),), constraints=("policy", "policy"))
    with pytest.raises(ValueError):
        Objective("Bad", ObjectiveOrigin.REQUESTED, (criterion(),), constraints=(" policy",))
