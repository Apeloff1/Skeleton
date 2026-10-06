from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.runtime.contracts.ai_execution import AIExecutionRequest, AIExecutionResult
from skeleton.ai.runtime.contracts.execution_authority import (
    ExecutionAuthority,
    ExecutionAuthorityError,
    ResourceBudget,
    ResourceUsage,
    authority_policy_digest,
    bind_authority_evidence,
    verify_authority_receipt_chain,
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
    policy_digest: str | None = None,
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
        policy_digest=policy_digest or parent.policy_digest,
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



def test_allow_emits_hash_chained_consumption_receipt() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    first = guard.authorize(
        authority=authority,
        capability="repo.read",
        delta=ResourceUsage(provider_calls=1, input_tokens=100),
        replay_key="read-001",
        now=NOW + timedelta(seconds=1),
    )
    second = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1, artifact_bytes=64),
        replay_key="write-001",
        now=NOW + timedelta(seconds=2),
    )

    assert first.receipt is not None
    assert second.receipt is not None
    assert first.receipt.sequence == 1
    assert first.receipt.previous_receipt_digest is None
    assert second.receipt.sequence == 2
    assert second.receipt.previous_receipt_digest == first.receipt.digest
    assert second.receipt.total_usage.provider_calls == 1
    assert second.receipt.total_usage.tool_calls == 1
    assert second.receipt.total_usage.artifact_bytes == 64


def test_authorization_replay_returns_identical_receipt_without_advancing_chain() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    delta = ResourceUsage(tool_calls=1)

    first = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=delta,
        replay_key="write-001",
        now=NOW + timedelta(seconds=1),
    )
    replay = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=delta,
        replay_key="write-001",
        now=NOW + timedelta(seconds=20),
    )

    assert first.receipt is not None
    assert replay.receipt == first.receipt
    assert replay.receipt.digest == first.receipt.digest
    assert guard.snapshot()["authorities"][0]["consumption_count"] == 1
    assert guard.snapshot()["authorization_receipt_count"] == 1


def test_denial_does_not_advance_consumption_chain() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority(budget=_budget(tool_calls=1))
    _admit(guard, authority)

    allowed = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="write-001",
        now=NOW + timedelta(seconds=1),
    )
    denied = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="write-002",
        now=NOW + timedelta(seconds=2),
    )

    assert allowed.receipt is not None
    assert denied.receipt is None
    snapshot = guard.snapshot()["authorities"][0]
    assert snapshot["consumption_count"] == 1
    assert snapshot["latest_receipt_digest"] == allowed.receipt.digest


def test_receipt_chain_verifier_reconstructs_exact_usage() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    decisions = [
        guard.authorize(
            authority=authority,
            capability="repo.read",
            delta=ResourceUsage(provider_calls=1, input_tokens=80),
            replay_key="read-001",
            now=NOW + timedelta(seconds=1),
        ),
        guard.authorize(
            authority=authority,
            capability="repo.write",
            delta=ResourceUsage(tool_calls=1, output_tokens=40),
            replay_key="write-001",
            now=NOW + timedelta(seconds=2),
        ),
    ]
    receipts = [decision.receipt for decision in decisions]
    assert all(receipt is not None for receipt in receipts)

    reconstructed = verify_authority_receipt_chain(
        authority,
        [receipt for receipt in receipts if receipt is not None],
    )

    assert reconstructed == guard.usage_for(authority)


def test_receipt_chain_verifier_rejects_missing_middle_receipt() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    first = guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-001",
        now=NOW + timedelta(seconds=1),
    )
    second = guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-002",
        now=NOW + timedelta(seconds=2),
    )
    third = guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-003",
        now=NOW + timedelta(seconds=3),
    )

    assert first.receipt is not None
    assert second.receipt is not None
    assert third.receipt is not None
    with pytest.raises(ExecutionAuthorityError, match="sequence is not contiguous"):
        verify_authority_receipt_chain(
            authority,
            [first.receipt, third.receipt],
        )


def test_sealed_evidence_binds_admission_latest_receipt_and_usage() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    decision = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1, artifact_bytes=256),
        replay_key="write-001",
        now=NOW + timedelta(seconds=1),
    )
    assert decision.receipt is not None

    evidence = guard.seal_evidence(
        authority,
        now=NOW + timedelta(seconds=2),
    )

    assert evidence.authority_digest == authority.digest
    assert evidence.consumption_count == 1
    assert evidence.latest_consumption_digest == decision.receipt.digest
    assert evidence.final_usage == guard.usage_for(authority)
    assert evidence.digest



def test_replay_capacity_fails_closed_instead_of_forgetting_side_effects() -> None:
    guard = ExecutionAuthorityGuard(max_replay_keys=2)
    authority = _authority(budget=_budget(tool_calls=3))
    _admit(guard, authority)

    first = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="write-001",
        now=NOW + timedelta(seconds=1),
    )
    assert first.allowed

    with pytest.raises(
        ExecutionAuthorityError,
        match="replay guard capacity exhausted",
    ):
        guard.authorize(
            authority=authority,
            capability="repo.write",
            delta=ResourceUsage(tool_calls=1),
            replay_key="write-002",
            now=NOW + timedelta(seconds=2),
        )

    replay = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="write-001",
        now=NOW + timedelta(seconds=3),
    )
    assert replay.disposition is AuthorizationDisposition.REPLAY
    assert guard.usage_for(authority).tool_calls == 1


def test_authority_capacity_fails_closed_instead_of_resetting_usage() -> None:
    guard = ExecutionAuthorityGuard(max_authorities=1, max_replay_keys=4)
    authority = _authority(budget=_budget(tool_calls=1))
    _admit(guard, authority)
    allowed = guard.authorize(
        authority=authority,
        capability="repo.write",
        delta=ResourceUsage(tool_calls=1),
        replay_key="write-001",
        now=NOW + timedelta(seconds=1),
    )
    assert allowed.allowed

    second = ExecutionAuthority(
        authority_id="authority-002",
        operation_id="operation-002",
        execution_id="execution-002",
        actor_id="agent.builder",
        issuer_id="supervisor",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        capabilities=("repo.read",),
        budget=_budget(),
        policy_digest=authority.policy_digest,
        nonce="nonce-002",
    )
    second_request = AIExecutionRequest(
        operation_id="operation-002",
        execution_id="execution-002",
        objective="Second authority must not evict first usage state.",
        context_policy={"mode": "bounded"},
        tool_policy={"default": "deny"},
        resource_budget={"profile": "authority-test"},
        stop_policy={"deadline": "required"},
        created_at=NOW,
    )
    with pytest.raises(
        ExecutionAuthorityError,
        match="authority guard capacity exhausted",
    ):
        guard.admit(
            authority=second,
            request=second_request,
            receipt_id="receipt-002",
            replay_key="admission-002",
            now=NOW + timedelta(seconds=2),
        )

    assert guard.usage_for(authority).tool_calls == 1


def test_concurrent_authorizations_are_serialized_into_one_valid_receipt_chain() -> None:
    guard = ExecutionAuthorityGuard(max_replay_keys=128)
    authority = _authority(
        budget=_budget(tool_calls=32, artifact_bytes=32_000),
    )
    _admit(guard, authority)

    def authorize(index: int):
        return guard.authorize(
            authority=authority,
            capability="repo.write",
            delta=ResourceUsage(tool_calls=1, artifact_bytes=10),
            replay_key=f"write-{index:03d}",
            now=NOW + timedelta(seconds=1),
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        decisions = list(executor.map(authorize, range(32)))

    assert all(decision.allowed for decision in decisions)
    receipts = [decision.receipt for decision in decisions]
    assert all(receipt is not None for receipt in receipts)
    ordered = sorted(
        (receipt for receipt in receipts if receipt is not None),
        key=lambda receipt: receipt.sequence,
    )
    assert [receipt.sequence for receipt in ordered] == list(range(1, 33))
    reconstructed = verify_authority_receipt_chain(authority, ordered)
    assert reconstructed.tool_calls == 32
    assert reconstructed.artifact_bytes == 320
    assert reconstructed == guard.usage_for(authority)



def test_future_dated_authority_is_not_active_before_issuance() -> None:
    authority = ExecutionAuthority(
        authority_id="authority-future",
        operation_id="operation-001",
        execution_id="execution-001",
        actor_id="agent.builder",
        issuer_id="supervisor",
        issued_at=NOW + timedelta(seconds=10),
        expires_at=NOW + timedelta(minutes=10),
        capabilities=("repo.read",),
        budget=_budget(),
        policy_digest=authority_policy_digest({"mode": "fail_closed"}),
        nonce="nonce-future",
    )

    assert not authority.active(now=NOW)
    assert not authority.permits("repo.read", now=NOW)

    guard = ExecutionAuthorityGuard()
    with pytest.raises(ExecutionAuthorityError, match="not active yet"):
        guard.admit(
            authority=authority,
            request=_request(),
            receipt_id="receipt-future",
            replay_key="admission-future",
            now=NOW,
        )


def test_authorization_clock_regression_is_denied_without_advancing_chain() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)

    first = guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-later",
        now=NOW + timedelta(seconds=10),
    )
    regressed = guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-earlier",
        now=NOW + timedelta(seconds=9),
    )

    assert first.allowed
    assert regressed.disposition is AuthorizationDisposition.DENY
    assert regressed.reason == "authorization time regressed"
    assert guard.snapshot()["authorities"][0]["consumption_count"] == 1


def test_sealed_evidence_has_stable_execution_lineage_reference() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-001",
        now=NOW + timedelta(seconds=1),
    )

    evidence = guard.seal_evidence(
        authority,
        now=NOW + timedelta(seconds=2),
    )
    payload = evidence.as_execution_evidence()

    assert evidence.evidence_ref == f"execution-authority-evidence:{evidence.digest}"
    assert payload["ref"] == evidence.evidence_ref
    assert payload["digest"] == evidence.digest
    assert payload["payload"] == evidence.canonical_payload()



def test_authority_evidence_binds_to_immutable_execution_result() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    guard.authorize(
        authority=authority,
        capability="repo.read",
        replay_key="read-001",
        now=NOW + timedelta(seconds=1),
    )
    evidence = guard.seal_evidence(
        authority,
        now=NOW + timedelta(seconds=2),
    )
    original = AIExecutionResult(
        operation_id=authority.operation_id,
        execution_id=authority.execution_id,
        status="completed",
        usage=guard.usage_for(authority).as_dict(),
        completed_at=NOW + timedelta(seconds=3),
        final_output="done",
    )

    bound = bind_authority_evidence(original, evidence)

    assert original.evidence_refs == ()
    assert bound.evidence_refs == (evidence.evidence_ref,)
    assert bound.operation_id == original.operation_id
    assert bound.execution_id == original.execution_id


def test_authority_evidence_binding_rejects_cross_execution_mixup() -> None:
    guard = ExecutionAuthorityGuard()
    authority = _authority()
    _admit(guard, authority)
    evidence = guard.seal_evidence(
        authority,
        now=NOW + timedelta(seconds=1),
    )
    foreign = AIExecutionResult(
        operation_id=authority.operation_id,
        execution_id="execution-foreign",
        status="completed",
        usage={},
        completed_at=NOW + timedelta(seconds=2),
        final_output="done",
    )

    with pytest.raises(
        ExecutionAuthorityError,
        match="execution_id does not match",
    ):
        bind_authority_evidence(foreign, evidence)



def test_delegated_authority_cannot_change_policy_digest() -> None:
    guard = ExecutionAuthorityGuard()
    parent = _authority()
    _admit(guard, parent)
    child = _child_authority(
        parent,
        policy_digest=authority_policy_digest(
            {"mode": "different-policy", "default": "allow"}
        ),
    )

    with pytest.raises(
        ExecutionAuthorityError,
        match="cannot change policy without refinement evidence",
    ):
        guard.admit(
            authority=child,
            request=_request(),
            receipt_id="receipt-child-policy-drift",
            replay_key="admission-child-policy-drift",
            now=NOW + timedelta(seconds=2),
        )
