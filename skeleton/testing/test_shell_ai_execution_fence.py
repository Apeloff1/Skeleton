"""Distributed AI execution fence regression and adversarial tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    InMemoryFencedStore,
    LeaseConflict,
)
from skeleton.shells.ai.execution_fence import (
    AIExecutionFence,
    AIExecutionFenceBinding,
    AIExecutionFenceError,
    AIExecutionFenceManager,
    AIExecutionFencePolicy,
)
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.runner import ShellCommand


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def plan(
    *,
    first_timeout: float | None = 2.0,
    second_timeout: float | None = 3.0,
    plan_id: str = "plan",
) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id,
        (
            PlanStep(
                "one",
                ShellCommand(
                    "python",
                    ("-V",),
                    timeout=first_timeout,
                ),
            ),
            PlanStep(
                "two",
                ShellCommand(
                    "python",
                    ("--help",),
                    timeout=second_timeout,
                ),
                depends_on=frozenset({"one"}),
            ),
        ),
    )


def policy(**changes) -> AIExecutionFencePolicy:
    values = dict(
        default_step_timeout_seconds=10.0,
        per_step_overhead_seconds=0.5,
        safety_margin_seconds=2.0,
        minimum_ttl_seconds=3.0,
        maximum_ttl_seconds=100.0,
        max_plan_steps=16,
    )
    values.update(changes)
    return AIExecutionFencePolicy(**values)


def manager(
    backend=None,
    *,
    item_policy: AIExecutionFencePolicy | None = None,
) -> AIExecutionFenceManager:
    return AIExecutionFenceManager(
        backend or InMemoryFencedStore(),
        policy=item_policy or policy(),
    )


def acquire(
    target: AIExecutionFenceManager,
    item_plan: ExecutionPlan | None = None,
    **changes,
) -> AIExecutionFence:
    values = dict(
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    values.update(changes)
    return target.acquire(item_plan or plan(), **values)


def require(
    target: AIExecutionFenceManager,
    fence: AIExecutionFence,
    item_plan: ExecutionPlan | None = None,
    **changes,
) -> AIExecutionFence:
    values = dict(
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    values.update(changes)
    return target.require(
        fence,
        item_plan or plan(),
        **values,
    )


def test_execution_fence_policy_digest_is_deterministic():
    item = policy()
    assert len(item.digest) == 64
    assert item.digest == item.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("default_step_timeout_seconds", 11.0),
        ("per_step_overhead_seconds", 0.6),
        ("safety_margin_seconds", 3.0),
        ("minimum_ttl_seconds", 4.0),
        ("maximum_ttl_seconds", 101.0),
        ("max_plan_steps", 17),
    ],
)
def test_execution_fence_policy_digest_changes(field, value):
    original = policy()
    changed = policy(**{field: value})
    assert original.digest != changed.digest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"default_step_timeout_seconds": 0},
        {"default_step_timeout_seconds": -1},
        {"per_step_overhead_seconds": -1},
        {"safety_margin_seconds": -1},
        {"minimum_ttl_seconds": 0},
        {"maximum_ttl_seconds": 0},
        {"max_plan_steps": 0},
    ],
)
def test_execution_fence_policy_validation(kwargs):
    with pytest.raises(ValueError):
        policy(**kwargs)


def test_execution_fence_policy_rejects_maximum_below_minimum():
    with pytest.raises(ValueError, match="maximum"):
        policy(
            minimum_ttl_seconds=10,
            maximum_ttl_seconds=9,
        )


def test_required_window_sums_serial_plan_timeouts():
    item = policy()
    # 2 + 3 + two 0.5 overheads + 2 safety.
    assert item.required_window(plan()) == 8.0


def test_required_window_uses_default_timeout_for_none():
    item = policy()
    assert item.required_window(
        plan(first_timeout=None, second_timeout=None)
    ) == 23.0


def test_required_window_respects_minimum():
    item = policy(
        per_step_overhead_seconds=0,
        safety_margin_seconds=0,
        minimum_ttl_seconds=10,
    )
    assert item.required_window(
        plan(first_timeout=1, second_timeout=1)
    ) == 10


def test_required_window_rejects_plan_above_maximum_ttl():
    item = policy(maximum_ttl_seconds=5)
    with pytest.raises(ValueError, match="wall-time"):
        item.required_window(plan())


def test_required_window_rejects_too_many_steps():
    item = policy(max_plan_steps=1)
    with pytest.raises(ValueError, match="step bound"):
        item.required_window(plan())


@pytest.mark.parametrize(
    "timeout",
    [0, -1, float("inf"), float("nan")],
)
def test_required_window_rejects_invalid_explicit_step_timeout(timeout):
    item = policy()
    with pytest.raises(ValueError, match="timeout"):
        item.required_window(
            plan(first_timeout=timeout)
        )


def test_execution_fence_binding_digest_is_deterministic():
    target = manager()
    binding = target.binding(
        plan(),
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    assert len(binding.digest) == 64
    assert binding.digest == binding.digest


def test_execution_fence_binding_contains_policy_and_window():
    target = manager()
    binding = target.binding(
        plan(),
        session_id="session",
        principal="alice",
        worker_id="worker-1",
    )
    assert binding.policy_digest == target.policy.digest
    assert binding.required_window_seconds == 8.0
    assert binding.plan_fingerprint == plan().fingerprint


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other"),
        ("principal", "bob"),
        ("worker_id", "worker-2"),
        ("plan_fingerprint", fp("x")),
        ("runtime_trust_digest", fp("x")),
        ("release_evidence_digest", fp("x")),
        ("required_window_seconds", 9.0),
        ("policy_digest", fp("x")),
    ],
)
def test_execution_fence_binding_digest_changes_for_authority_surface(
    field,
    value,
):
    original = AIExecutionFenceBinding(
        1,
        "session",
        "alice",
        "worker-1",
        fp("p"),
        fp("t"),
        fp("r"),
        8.0,
        fp("q"),
    )
    changed = replace(original, **{field: value})
    assert changed.digest != original.digest


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"session_id": ""},
        {"principal": ""},
        {"worker_id": ""},
        {"plan_fingerprint": "bad"},
        {"runtime_trust_digest": "bad"},
        {"release_evidence_digest": "bad"},
        {"required_window_seconds": 0},
        {"policy_digest": "bad"},
    ],
)
def test_execution_fence_binding_validation(changes):
    values = dict(
        schema_version=1,
        session_id="session",
        principal="alice",
        worker_id="worker-1",
        plan_fingerprint=fp("p"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
        required_window_seconds=8.0,
        policy_digest=fp("q"),
    )
    values.update(changes)
    with pytest.raises(ValueError):
        AIExecutionFenceBinding(**values)


def test_execution_fence_acquire_happy_path():
    target = manager()
    fence = acquire(target)
    assert fence.binding.session_id == "session"
    assert fence.binding.worker_id == "worker-1"
    assert fence.lease.owner == "worker-1"
    assert fence.lease.fencing_token == 1
    assert fence.lease.namespace == "shell-ai-execution-fence"
    assert len(fence.digest) == 64
    assert require(target, fence) == fence


def test_execution_fence_to_dict_contains_binding_and_lease():
    target = manager()
    fence = acquire(target)
    data = fence.to_dict()
    assert data["binding_digest"] == fence.binding.digest
    assert data["fence_digest"] == fence.digest
    assert data["lease"]["fencing_token"] == 1


def test_execution_fence_same_plan_conflicts_while_owned():
    backend = InMemoryFencedStore()
    first = manager(backend)
    second = manager(backend)
    acquire(first)
    with pytest.raises(LeaseConflict):
        acquire(second, worker_id="worker-2")


def test_execution_fence_different_session_has_distinct_resource():
    target = manager()
    one = acquire(target, session_id="one")
    two = acquire(target, session_id="two")
    assert one.lease.key != two.lease.key


def test_execution_fence_different_plan_has_distinct_resource():
    target = manager()
    one = acquire(target, plan(plan_id="one"))
    two = acquire(target, plan(plan_id="two"))
    assert one.lease.key != two.lease.key


def test_execution_fence_release_allows_reacquire_with_new_fencing_token():
    backend = InMemoryFencedStore()
    target = manager(backend)
    first = acquire(target)
    assert target.release(first)
    second = acquire(target)
    assert second.lease.fencing_token == first.lease.fencing_token + 1
    assert second.digest != first.digest


def test_execution_fence_old_owner_is_stale_after_reacquire():
    backend = InMemoryFencedStore()
    target = manager(backend)
    first = acquire(target)
    target.release(first)
    second = acquire(target)
    with pytest.raises(AIExecutionFenceError, match="stale"):
        require(target, first)
    assert require(target, second) == second


def test_execution_fence_expiry_rejects_stale_owner():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    target = manager(
        backend,
        item_policy=policy(
            default_step_timeout_seconds=1,
            per_step_overhead_seconds=0,
            safety_margin_seconds=0,
            minimum_ttl_seconds=1,
        ),
    )
    fence = acquire(
        target,
        plan(first_timeout=1, second_timeout=1),
        ttl_seconds=2,
    )
    now[0] = 2
    with pytest.raises(AIExecutionFenceError, match="stale"):
        require(
            target,
            fence,
            plan(first_timeout=1, second_timeout=1),
        )


def test_execution_fence_reacquire_after_expiry_increments_token():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    target = manager(
        backend,
        item_policy=policy(
            default_step_timeout_seconds=1,
            per_step_overhead_seconds=0,
            safety_margin_seconds=0,
            minimum_ttl_seconds=1,
        ),
    )
    item_plan = plan(first_timeout=1, second_timeout=1)
    first = acquire(target, item_plan, ttl_seconds=2)
    now[0] = 2
    second = acquire(target, item_plan, ttl_seconds=2)
    assert second.lease.fencing_token == first.lease.fencing_token + 1


def test_execution_fence_ttl_must_cover_plan_budget():
    target = manager()
    with pytest.raises(AIExecutionFenceError, match="cover"):
        acquire(target, ttl_seconds=7.9)


def test_execution_fence_ttl_may_equal_plan_budget():
    target = manager()
    fence = acquire(target, ttl_seconds=8.0)
    assert fence.lease.expires_at - fence.lease.acquired_at == 8.0


def test_execution_fence_ttl_cannot_exceed_policy_maximum():
    target = manager()
    with pytest.raises(AIExecutionFenceError, match="maximum"):
        acquire(target, ttl_seconds=101)


@pytest.mark.parametrize(
    "field,changes",
    [
        ("principal", {"principal": "bob"}),
        ("worker", {"worker_id": "worker-2"}),
        ("trust", {"runtime_trust_digest": fp("x")}),
        ("release", {"release_evidence_digest": fp("x")}),
        ("session", {"session_id": "other"}),
    ],
)
def test_execution_fence_require_rejects_binding_substitution(
    field,
    changes,
):
    target = manager()
    fence = acquire(target)
    with pytest.raises(AIExecutionFenceError, match="binding"):
        require(target, fence, **changes)


def test_execution_fence_require_rejects_plan_substitution():
    target = manager()
    fence = acquire(target)
    other = plan(plan_id="other")
    with pytest.raises(AIExecutionFenceError, match="binding"):
        require(target, fence, other)


def test_execution_fence_require_rejects_policy_change():
    backend = InMemoryFencedStore()
    first = manager(backend)
    fence = acquire(first)
    second = manager(
        backend,
        item_policy=policy(safety_margin_seconds=3),
    )
    with pytest.raises(AIExecutionFenceError, match="binding"):
        require(second, fence)


def test_execution_fence_renew_happy_path():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    target = manager(backend)
    fence = acquire(target)
    now[0] = 1
    renewed = target.renew(
        fence,
        plan(),
        ttl_seconds=20,
    )
    assert renewed.lease.fencing_token == fence.lease.fencing_token
    assert renewed.lease.acquired_at == fence.lease.acquired_at
    assert renewed.lease.expires_at == 21


def test_execution_fence_old_instance_is_stale_after_renew():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    target = manager(backend)
    fence = acquire(target)
    now[0] = 1
    renewed = target.renew(
        fence,
        plan(),
        ttl_seconds=20,
    )
    with pytest.raises(AIExecutionFenceError, match="stale"):
        require(target, fence)
    assert require(target, renewed) == renewed


def test_execution_fence_renew_ttl_must_cover_plan():
    target = manager()
    fence = acquire(target)
    with pytest.raises(AIExecutionFenceError, match="cover"):
        target.renew(
            fence,
            plan(),
            ttl_seconds=7,
        )


def test_execution_fence_renew_ttl_cannot_exceed_maximum():
    target = manager()
    fence = acquire(target)
    with pytest.raises(AIExecutionFenceError, match="maximum"):
        target.renew(
            fence,
            plan(),
            ttl_seconds=101,
        )


def test_execution_fence_release_is_idempotent_false_after_first():
    target = manager()
    fence = acquire(target)
    assert target.release(fence)
    assert not target.release(fence)


def test_execution_fence_digest_binds_fencing_token():
    backend = InMemoryFencedStore()
    target = manager(backend)
    first = acquire(target)
    target.release(first)
    second = acquire(target)
    assert first.binding == second.binding
    assert first.digest != second.digest


def test_execution_fence_digest_binds_expiry():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    target = manager(backend)
    first = acquire(target)
    target.release(first)
    second = acquire(target, ttl_seconds=20)
    assert first.digest != second.digest


def test_execution_fence_empty_optional_trust_and_release_supported():
    target = manager()
    fence = acquire(
        target,
        runtime_trust_digest="",
        release_evidence_digest="",
    )
    assert fence.binding.runtime_trust_digest == ""
    assert fence.binding.release_evidence_digest == ""
    assert require(
        target,
        fence,
        runtime_trust_digest="",
        release_evidence_digest="",
    ) == fence


def test_execution_fence_manager_rejects_invalid_namespace():
    with pytest.raises(ValueError, match="namespace"):
        AIExecutionFenceManager(
            InMemoryFencedStore(),
            namespace="",
        )


def test_execution_fence_manager_requires_fenced_backend():
    class NotABackend:
        pass

    with pytest.raises(TypeError, match="FencedLeaseBackend"):
        AIExecutionFenceManager(NotABackend())


def test_execution_fence_dataclass_requires_fenced_lease():
    target = manager()
    fence = acquire(target)
    with pytest.raises(ValueError, match="lease"):
        AIExecutionFence(fence.binding, object())


def test_execution_fence_dataclass_requires_binding():
    target = manager()
    fence = acquire(target)
    with pytest.raises(ValueError, match="binding"):
        AIExecutionFence(object(), fence.lease)


def test_execution_fence_resource_key_is_deterministic():
    first = AIExecutionFenceManager._resource_key("s", fp("p"))
    second = AIExecutionFenceManager._resource_key("s", fp("p"))
    assert first == second
    assert first.startswith("exec:")


def test_execution_fence_resource_key_changes_with_session():
    assert (
        AIExecutionFenceManager._resource_key("one", fp("p"))
        != AIExecutionFenceManager._resource_key("two", fp("p"))
    )


def test_execution_fence_resource_key_changes_with_plan():
    assert (
        AIExecutionFenceManager._resource_key("s", fp("a"))
        != AIExecutionFenceManager._resource_key("s", fp("b"))
    )
