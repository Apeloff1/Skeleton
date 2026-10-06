from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.runtime.contracts.ai_execution import AIExecutionRequest
from skeleton.ai.runtime.contracts.execution_authority import (
    ExecutionAuthority,
    ExecutionAuthorityError,
    ResourceBudget,
    ResourceUsage,
    authority_policy_digest,
)
from skeleton.ai.runtime.core.execution_authority import (
    AuthorizationDisposition,
    ExecutionAuthorityGuard,
)


NOW = datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)


def _budget(**overrides: int) -> ResourceBudget:
    values = {
        "provider_calls": 3,
        "tool_calls": 2,
        "input_tokens": 10_000,
        "output_tokens": 5_000,
        "artifact_bytes": 1_000_000,
        "wall_time_ms": 60_000,
        "parallelism": 2,
    }
    values.update(overrides)
    return ResourceBudget(**values)


def _authority(
    *,
    capabilities: tuple[str, ...] = ("repo.read", "repo.write"),
    budget: ResourceBudget | None = None,
    expires_delta: timedelta = timedelta(minutes=30),
) -> ExecutionAuthority:
    return ExecutionAuthority(
        authority_id="authority-001",
        operation_id="operation-001",
        execution_id="execution-001",
        actor_id="agent.builder",
        issuer_id="supervisor",
        issued_at=NOW,
        expires_at=NOW + expires_delta,
        capabilities=capabilities,
        budget=budget or _budget(),
        policy_digest=authority_policy_digest(
            {"mode": "fail_closed", "scope": "skeleton/ai"}
        ),
        nonce="nonce-001",
    )


def _request() -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id="operation-001",
        execution_id="execution-001",
        objective="Harden the AI execution authority boundary.",
        context_policy={"mode": "bounded"},
        tool_policy={"default": "deny"},
        resource_budget={"profile": "authority-test"},
        stop_policy={"deadline": "required"},
        created_at=NOW,
    )


def _admit(
    guard: ExecutionAuthorityGuard,
    authority: ExecutionAuthority,
) -> None:
    guard.admit(
        authority=authority,
        request=_request(),
        receipt_id="receipt-001",
        replay_key="admission-001",
        now=NOW,
    )


def test_authority_digest_is_canonical_across_capability_order_and_duplicates() -> None:
    left = _authority(capabilities=("repo.write", "repo.read", "repo.read"))
    right = _authority(capabilities=("repo.read", "repo.write"))

    assert left.capabilities == ("repo.read", "repo.write")
    assert left.digest == right.digest


def test_authority_expiry_is_fail_closed_at_boundary() -> None:
    authority = _authority(expires_delta=timedelta(seconds=10))

    assert authority.permits("repo.read", now=NOW + timedelta(seconds=9))
    assert not authority.permits("repo.read", now=NOW + timedelta(seconds=10))


def test_admission_binds_operation_and_execution_identity() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    request = _request()
    mismatched = AIExecutionRequest(
        operation_id=request.operation_id,
        execution_id="execution-other",
        objective=request.objective,
        context_policy=request.context_policy,
        tool_policy=request.tool_policy,
        resource_budget=request.resource_budget,
        stop_policy=request.stop_policy,
        created_at=request.created_at,
    )

    with pytest.raises(ExecutionAuthorityError, match="execution identity mismatch"):
        guard.admit(
            authority=authority,
            request=mismatched,
            receipt_id="receipt-001",
            replay_key="admission-001",
            now=NOW,
        )


def test_unknown_capability_is_denied_without_consuming_budget() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    decision = guard.authorize(
        authority=authority,
        capability="repo.admin",
        delta=ResourceUsage(tool_calls=1),
        replay_key="tool-001",
        now=NOW,
    )

    assert decision.disposition is AuthorizationDisposition.DENY
    assert guard.usage_for(authority).tool_calls == 0


def test_budget_is_monotonic_and_exhaustion_fails_closed() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority(budget=_budget(tool_calls=1))
    _admit(guard, authority)

    first = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="tool-001",
        now=NOW,
    )
    second = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="tool-002",
        now=NOW,
    )

    assert first.allowed
    assert second.disposition is AuthorizationDisposition.DENY
    assert guard.usage_for(authority).tool_calls == 1


def test_identical_replay_is_not_double_accounted() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    delta = ResourceUsage(tool_calls=1, artifact_bytes=32)

    first = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=delta,
        replay_key="tool-001",
        now=NOW,
    )
    replay = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=delta,
        replay_key="tool-001",
        now=NOW,
    )

    assert first.disposition is AuthorizationDisposition.ALLOW
    assert replay.disposition is AuthorizationDisposition.REPLAY
    assert guard.usage_for(authority).tool_calls == 1
    assert guard.usage_for(authority).artifact_bytes == 32


def test_changed_replay_payload_is_rejected() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="tool-001",
        now=NOW,
    )

    with pytest.raises(
        ExecutionAuthorityError,
        match="replay_key reused with different authorization payload",
    ):
        guard.authorize(
            authority=authority,
            capability="repo.write",
            delta=ResourceUsage(tool_calls=1, artifact_bytes=1),
            replay_key="tool-001",
            now=NOW,
        )


def test_revocation_denies_future_use_without_erasing_usage() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    allowed = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="tool-001",
        now=NOW,
    )
    guard.revoke(authority)
    denied = guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-001",
        now=NOW,
    )

    assert allowed.allowed
    assert denied.disposition is AuthorizationDisposition.DENY
    assert denied.reason == "authority is revoked"
    assert guard.usage_for(authority).tool_calls == 1


def test_parallelism_budget_uses_high_water_mark() -> None:
    current = ResourceUsage(parallelism=1)
    projected = current.add(ResourceUsage(parallelism=2))

    assert projected.parallelism == 2
    assert _budget(parallelism=2).permits(projected)
    assert not _budget(parallelism=1).permits(projected)


def test_snapshot_is_stable_and_contains_no_mutable_authority_object() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    guard.authorize(
        authority=authority,
        capability="repo.read",
        delta=ResourceUsage(provider_calls=1),
        replay_key="provider-001",
        now=NOW,
    )

    snapshot = guard.snapshot()

    assert snapshot["authority_count"] == 1
    assert snapshot["authorities"][0]["authority_digest"] == authority.digest
    assert snapshot["authorities"][0]["usage"]["provider_calls"] == 1



def _child_authority(
    parent: ExecutionAuthority,
    *,
    capabilities: tuple[str, ...] = ("repo.read",),
    budget: ResourceBudget | None = None,
    actor_id: str = "agent.worker",
    expires_at: datetime | None = None,
) -> ExecutionAuthority:
    return ExecutionAuthority(
        authority_id="authority-child-001",
        operation_id=parent.operation_id,
        execution_id=parent.execution_id,
        actor_id=actor_id,
        issuer_id=parent.actor_id,
        issued_at=NOW + timedelta(seconds=1),
        expires_at=expires_at or (NOW + timedelta(minutes=20)),
        capabilities=capabilities,
        budget=budget or _budget(tool_calls=1, parallelism=1),
        policy_digest=parent.policy_digest,
        nonce="nonce-child-001",
        parent_authority_digest=parent.digest,
    )


def test_admission_replay_returns_original_receipt() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()

    first = guard.admit(
        authority=authority,
        request=_request(),
        receipt_id="receipt-001",
        replay_key="admission-001",
        now=NOW,
    )
    replay = guard.admit(
        authority=authority,
        request=_request(),
        receipt_id="receipt-different",
        replay_key="admission-001",
        now=NOW + timedelta(seconds=5),
    )

    assert replay == first
    assert replay.digest == first.digest
    assert guard.snapshot()["admission_receipt_count"] == 1


def test_delegated_authority_requires_admitted_parent() -> None:
    guard = ExecutionAuthorityGuard()
    parent = _authority()
    child = _child_authority(parent)

    with pytest.raises(ExecutionAuthorityError, match="parent authority has not been admitted"):
        guard.admit(
            authority=child,
            request=_request(),
            receipt_id="receipt-child",
            replay_key="admission-child",
            now=NOW + timedelta(seconds=2),
        )


def test_delegated_authority_can_only_attenuate_parent() -> None:
    guard = ExecutionAuthorityGuard()
    parent = _authority()
    _admit(guard, parent)

    child = _child_authority(parent)
    receipt = guard.admit(
        authority=child,
        request=_request(),
        receipt_id="receipt-child",
        replay_key="admission-child",
        now=NOW + timedelta(seconds=2),
    )

    assert receipt.authority_digest == child.digest

    escalated = _child_authority(
        parent,
        capabilities=("repo.read", "repo.write", "repo.admin"),
    )
    with pytest.raises(ExecutionAuthorityError, match="escalates capabilities"):
        guard.admit(
            authority=escalated,
            request=_request(),
            receipt_id="receipt-escalated",
            replay_key="admission-escalated",
            now=NOW + timedelta(seconds=2),
        )


def test_delegated_authority_cannot_outlive_parent_or_expand_budget() -> None:
    guard = ExecutionAuthorityGuard()
    parent = _authority()
    _admit(guard, parent)

    outliving = _child_authority(
        parent,
        expires_at=parent.expires_at + timedelta(seconds=1),
    )
    with pytest.raises(ExecutionAuthorityError, match="outlives parent"):
        guard.admit(
            authority=outliving,
            request=_request(),
            receipt_id="receipt-outliving",
            replay_key="admission-outliving",
            now=NOW + timedelta(seconds=2),
        )

    expanded = _child_authority(
        parent,
        budget=_budget(tool_calls=parent.budget.tool_calls + 1),
    )
    with pytest.raises(ExecutionAuthorityError, match="escalates resource budget"):
        guard.admit(
            authority=expanded,
            request=_request(),
            receipt_id="receipt-expanded",
            replay_key="admission-expanded",
            now=NOW + timedelta(seconds=2),
        )


def test_replay_key_is_bounded_and_canonical() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    with pytest.raises(ExecutionAuthorityError, match="invalid replay_key"):
        guard.authorize(
            authority=authority,
            capability="repo.read",
            replay_key=" contains spaces ",
            now=NOW,
        )



def test_revoked_ancestor_invalidates_admitted_child() -> None:
    guard = ExecutionAuthorityGuard()
    parent = _authority()
    _admit(guard, parent)
    child = _child_authority(parent)
    guard.admit(
        authority=child,
        request=_request(),
        receipt_id="receipt-child",
        replay_key="admission-child",
        now=NOW + timedelta(seconds=2),
    )

    guard.revoke(parent)
    decision = guard.authorize(
        authority=child,
        capability="repo.read",
        replay_key="child-read-001",
        now=NOW + timedelta(seconds=3),
    )

    assert decision.disposition is AuthorizationDisposition.DENY
    assert decision.reason == "ancestor authority is revoked"
