from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.network.remote_execution import (
    RemoteExecutionError,
    RemoteExecutionRequest,
    RemoteExecutionResult,
    RemoteResultStatus,
    WorkerAttestation,
    issue_remote_execution_fence,
    qualify_remote_execution,
    qualify_remote_execution_commit,
    worker_identity_digest,
)
from skeleton.shells.leases import Lease, LeaseRegistry
from skeleton.shells.worker_heartbeat import (
    HeartbeatPolicy,
    HeartbeatRegistry,
    LivenessView,
    WorkerLiveness,
)
from skeleton.shells.worker_identity import (
    WorkerIdentity,
    WorkerRegistry,
    WorkerRole,
)
from skeleton.shells.worker_protocol import (
    ProtocolGuard,
    WorkerMessage,
    WorkerMessageKind,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _worker(*, generation: int = 1) -> WorkerIdentity:
    return WorkerIdentity(
        worker_id="worker-a",
        generation=generation,
        role=WorkerRole.EXECUTOR,
        labels={"region": "eu-north", "trust": "prod"},
        features=frozenset({"remote-exec", "sandbox-v1"}),
        protocol_version=1,
    )


def _request(**overrides: object) -> RemoteExecutionRequest:
    values: dict[str, object] = {
        "operation_id": "operation-1",
        "execution_id": "execution-1",
        "tenant_id": "tenant-a",
        "request_id": "request-1",
        "coordinator_id": "coordinator-1",
        "action_digest": "a" * 64,
        "authority_digest": "b" * 64,
        "payload_digest": "c" * 64,
        "required_role": WorkerRole.EXECUTOR,
        "required_features": ("remote-exec",),
        "required_labels": (("region", "eu-north"),),
        "protocol_version": 1,
        "max_tokens": 1000,
        "max_cost_units": 10.0,
        "max_wall_time_s": 60.0,
    }
    values.update(overrides)
    return RemoteExecutionRequest(**values)


def _attestation(
    worker: WorkerIdentity,
    *,
    observed_at: float = 100.0,
    expires_at: float = 200.0,
    **overrides: object,
) -> WorkerAttestation:
    values: dict[str, object] = {
        "worker_id": worker.worker_id,
        "generation": worker.generation,
        "identity_digest": worker_identity_digest(worker),
        "runtime_digest": "d" * 64,
        "image_digest": "e" * 64,
        "policy_digest": "f" * 64,
        "verifier_id": "verifier:worker-trust",
        "verifier_digest": "1" * 64,
        "evidence_refs": (
            EvidenceRef(
                source="worker://attestation/worker-a",
                digest="2" * 64,
                category="worker_attestation",
            ),
        ),
        "observed_at": observed_at,
        "expires_at": expires_at,
        "independent": True,
    }
    values.update(overrides)
    return WorkerAttestation(**values)


def _runtime():
    clock = Clock()
    workers = WorkerRegistry(clock=clock)
    worker = _worker()
    registration = workers.register(worker)
    heartbeats = HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(
            late_after_seconds=5.0,
            stale_after_seconds=10.0,
        ),
        clock=clock,
    )
    heartbeats.beat(worker, sequence=1)
    request = _request()
    leases = LeaseRegistry(clock=clock)
    lease = leases.acquire(
        request.lease_key,
        worker.key,
        ttl_seconds=30.0,
    )
    fence = issue_remote_execution_fence(
        request=request,
        worker=worker,
        lease=lease,
    )
    attestation = _attestation(worker)
    liveness = heartbeats.liveness(worker)
    grant = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=clock(),
    )
    return (
        clock,
        workers,
        heartbeats,
        leases,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    )


def _completion_chain(
    worker: WorkerIdentity,
    request: RemoteExecutionRequest,
    grant,
    fence,
    *,
    tokens_used: int = 100,
    cost_units: float = 1.0,
    wall_time_s: float = 5.0,
    status: RemoteResultStatus = RemoteResultStatus.SUCCEEDED,
):
    result = RemoteExecutionResult(
        request_digest=request.request_digest,
        grant_digest=grant.decision_digest,
        worker_identity_digest=worker_identity_digest(worker),
        fence_digest=fence.fence_digest,
        output_digest="3" * 64,
        status=status,
        tokens_used=tokens_used,
        cost_units=cost_units,
        wall_time_s=wall_time_s,
        started_at=101.0,
        completed_at=106.0,
    )
    message = WorkerMessage(
        message_id="complete-1",
        sequence=1,
        kind=WorkerMessageKind.COMPLETE,
        sender=worker,
        recipient=request.coordinator_id,
        payload={
            "request_digest": request.request_digest,
            "grant_digest": grant.decision_digest,
            "fence_digest": fence.fence_digest,
            "result_digest": result.result_digest,
        },
        protocol_version=request.protocol_version,
        correlation_id=request.request_id,
    )
    guard = ProtocolGuard(protocol_version=request.protocol_version)
    cursor = guard.accept(message)
    return result, message, cursor, guard


def test_healthy_attested_worker_receives_grant_and_commit() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()

    assert grant.accepted is True
    assert grant.reasons == ()

    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )
    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is True
    assert commit.reasons == ()
    evidence = commit.accepted_evidence_ref()
    assert evidence.category == "remote_execution_commit"
    assert evidence.digest == commit.decision_digest


def test_partition_stales_worker_and_blocks_commit() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )

    clock.advance(11.0)
    assert heartbeats.liveness(worker).liveness is WorkerLiveness.STALE

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert "commit-worker-liveness-stale" in commit.reasons


def test_late_worker_is_not_commit_authority() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        _,
    ) = _runtime()
    clock.advance(6.0)
    liveness = heartbeats.liveness(worker)
    assert liveness.liveness is WorkerLiveness.LATE

    decision = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=clock(),
    )

    assert decision.accepted is False
    assert "worker-liveness-late" in decision.reasons


def test_unattested_identity_digest_blocks_grant() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        _,
    ) = _runtime()
    attestation = replace(
        attestation,
        identity_digest="0" * 64,
    )

    decision = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=clock(),
    )

    assert decision.accepted is False
    assert "attestation-identity-digest-mismatch" in decision.reasons


def test_expired_attestation_blocks_grant() -> None:
    (
        _,
        _,
        _,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        _,
        _,
    ) = _runtime()
    attestation = _attestation(
        worker,
        observed_at=50.0,
        expires_at=99.0,
    )
    liveness = LivenessView(
        worker.worker_id,
        worker.generation,
        WorkerLiveness.HEALTHY,
        0.1,
        2,
        False,
        0,
    )

    decision = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=100.0,
    )

    assert decision.accepted is False
    assert "attestation-expired" in decision.reasons


def test_attestation_must_be_independent() -> None:
    worker = _worker()
    with pytest.raises(
        RemoteExecutionError,
        match="must be independent",
    ):
        _attestation(worker, independent=False)


def test_replaced_worker_generation_cannot_use_old_grant() -> None:
    (
        clock,
        workers,
        _,
        _,
        worker,
        _,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    replacement = _worker(generation=2)
    replacement_registration = workers.replace(replacement)
    liveness = LivenessView(
        worker.worker_id,
        worker.generation,
        WorkerLiveness.HEALTHY,
        0.1,
        2,
        False,
        0,
    )
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=replacement_registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert "commit-worker-registration-identity-mismatch" in commit.reasons
    assert "commit-worker-generation-stale" in commit.reasons


def test_disabled_worker_cannot_receive_grant() -> None:
    (
        clock,
        workers,
        heartbeats,
        _,
        worker,
        _,
        request,
        lease,
        fence,
        attestation,
        _,
    ) = _runtime()
    disabled = workers.set_enabled(worker, False)

    decision = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=disabled,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=clock(),
    )

    assert decision.accepted is False
    assert "worker-registration-disabled" in decision.reasons


@pytest.mark.parametrize(
    ("remote_request", "reason"),
    (
        (
            _request(required_role=WorkerRole.TESTER),
            "worker-role-mismatch",
        ),
        (
            _request(required_features=("gpu",)),
            "worker-feature-mismatch",
        ),
        (
            _request(required_labels=(("region", "us-west"),)),
            "worker-label-mismatch",
        ),
        (
            _request(protocol_version=2),
            "worker-protocol-version-mismatch",
        ),
    ),
)
def test_worker_capability_mismatch_blocks(
    remote_request: RemoteExecutionRequest,
    reason: str,
) -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        _,
        _,
        _,
        attestation,
        _,
    ) = _runtime()
    lease = Lease(
        "lease-capability",
        remote_request.lease_key,
        worker.key,
        90.0,
        130.0,
    )
    fence = issue_remote_execution_fence(
        request=remote_request,
        worker=worker,
        lease=lease,
    )

    decision = qualify_remote_execution(
        request=remote_request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=clock(),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_expired_lease_blocks_commit() -> None:
    (
        _,
        _,
        _,
        _,
        worker,
        registration,
        request,
        _,
        _,
        attestation,
        _,
    ) = _runtime()
    lease = Lease(
        "lease-expired",
        request.lease_key,
        worker.key,
        80.0,
        99.0,
    )
    fence = issue_remote_execution_fence(
        request=request,
        worker=worker,
        lease=lease,
    )
    liveness = LivenessView(
        worker.worker_id,
        worker.generation,
        WorkerLiveness.HEALTHY,
        0.1,
        2,
        False,
        0,
    )
    attestation = _attestation(
        worker,
        observed_at=80.0,
        expires_at=200.0,
    )
    grant = qualify_remote_execution(
        request=request,
        worker=worker,
        registration=registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        fence=fence,
        observed_at=90.0,
    )
    assert grant.accepted is True
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=liveness,
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=100.0,
    )

    assert commit.accepted is False
    assert "commit-lease-expired" in commit.reasons


def test_newer_fence_invalidates_old_worker_commit() -> None:
    (
        clock,
        _,
        heartbeats,
        leases,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )
    renewed = leases.renew(lease, ttl_seconds=30.0)
    current_fence = issue_remote_execution_fence(
        request=request,
        worker=worker,
        lease=renewed,
        previous=fence,
    )

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=renewed,
        current_fence=current_fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert "stale-fence" in commit.reasons
    assert "stale-fence-epoch" in commit.reasons
    assert "result-fence-mismatch" in commit.reasons


@pytest.mark.parametrize(
    ("tokens", "cost", "wall", "reason"),
    (
        (1001, 1.0, 5.0, "token-budget-exceeded"),
        (100, 10.1, 5.0, "cost-budget-exceeded"),
        (100, 1.0, 60.1, "wall-time-budget-exceeded"),
    ),
)
def test_result_budget_overrun_blocks_authoritative_commit(
    tokens: int,
    cost: float,
    wall: float,
    reason: str,
) -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, _, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
        tokens_used=tokens,
        cost_units=cost,
        wall_time_s=wall,
    )
    guard = ProtocolGuard()
    cursor = guard.accept(message)

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert reason in commit.reasons


def test_failed_result_cannot_commit_authoritative_effect() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
        status=RemoteResultStatus.FAILED,
    )

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert "result-not-successful" in commit.reasons


def test_protocol_guard_rejects_completion_replay() -> None:
    (
        _,
        _,
        _,
        _,
        worker,
        _,
        request,
        _,
        fence,
        _,
        grant,
    ) = _runtime()
    _, message, _, guard = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )

    with pytest.raises(RuntimeError, match="replay detected"):
        guard.accept(message)


def test_unaccepted_protocol_cursor_blocks_commit() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )
    stale_cursor = replace(
        cursor,
        last_sequence=message.sequence - 1,
    )

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=stale_cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert "protocol-cursor-sequence-mismatch" in commit.reasons


def test_completion_payload_substitution_blocks_commit() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, _, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
    )
    message = WorkerMessage(
        message_id=message.message_id,
        sequence=message.sequence,
        kind=message.kind,
        sender=message.sender,
        recipient=message.recipient,
        payload={
            **dict(message.payload),
            "result_digest": "0" * 64,
        },
        protocol_version=message.protocol_version,
        correlation_id=message.correlation_id,
    )
    cursor = ProtocolGuard().accept(message)

    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    assert "completion-payload-mismatch" in commit.reasons


def test_rejected_commit_cannot_materialize_promotion_evidence() -> None:
    (
        clock,
        _,
        heartbeats,
        _,
        worker,
        registration,
        request,
        lease,
        fence,
        attestation,
        grant,
    ) = _runtime()
    result, message, cursor, _ = _completion_chain(
        worker,
        request,
        grant,
        fence,
        status=RemoteResultStatus.FAILED,
    )
    commit = qualify_remote_execution_commit(
        request=request,
        worker=worker,
        registration=registration,
        liveness=heartbeats.liveness(worker),
        attestation=attestation,
        lease=lease,
        current_fence=fence,
        grant=grant,
        result=result,
        completion=message,
        protocol_cursor=cursor,
        observed_at=clock(),
    )

    assert commit.accepted is False
    with pytest.raises(
        RemoteExecutionError,
        match="cannot become promotion",
    ):
        commit.accepted_evidence_ref()
