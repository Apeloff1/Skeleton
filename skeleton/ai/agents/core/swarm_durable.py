"""Durable persistence bridge for the existing swarm recovery manager.

This module does not implement another scheduler or checkpoint format. It stores
``SwarmRecoveryManager``'s already-versioned, checksummed archive inside a
provider-neutral durable run store so swarm state survives process restarts
while the existing recovery manager remains the canonical swarm serializer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from collections.abc import Callable

from skeleton.automation.agents.swarm_recovery import (
    SUPPORTED_RECOVERY_ARCHIVE_VERSIONS, SwarmRecoveryManager,
)
from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState
from skeleton.automation.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.state import CheckpointRecord, ResumeState


@runtime_checkable
class DurableCheckpointStore(Protocol):
    """Minimal durable-store surface required by the swarm recovery bridge."""

    def checkpoint(
        self,
        run_id: str,
        state: Any,
        *,
        worker_id: str,
        after_step_id: str | None = None,
        state_version: int = 1,
    ) -> CheckpointRecord: ...

    def resume_state(self, run_id: str) -> ResumeState: ...


class DurableSwarmError(RuntimeError):
    """Raised when durable swarm state violates the bridge contract."""


@dataclass(frozen=True, slots=True)
class DurableSwarmCapture:
    """One swarm checkpoint captured and committed to durable storage."""

    swarm_sequence: int
    checkpoint: CheckpointRecord


@dataclass(frozen=True, slots=True)
class DurableSwarmRecovery:
    """Verified swarm recovery archive plus its outer run replay state."""

    manager: SwarmRecoveryManager
    checkpoint: CheckpointRecord
    resume: ResumeState

    def restore_runtime(self):
        """Restore legacy leases or hold fenced attempts for reconciliation."""
        return self.manager.restore_latest()


class SwarmDurableBridge:
    """Persist canonical swarm recovery archives through a durable checkpoint store."""

    def __init__(self, store: DurableCheckpointStore) -> None:
        if not isinstance(store, DurableCheckpointStore):
            raise TypeError("store must implement the durable checkpoint-store contract")
        self.store = store

    def persist(
        self,
        run_id: str,
        worker_id: str,
        manager: SwarmRecoveryManager,
        *,
        after_step_id: str | None = None,
    ) -> CheckpointRecord:
        """Persist the manager's verified bounded archive as one run checkpoint."""
        if not isinstance(manager, SwarmRecoveryManager):
            raise TypeError("manager must be a SwarmRecoveryManager")
        archive = manager.export_archive()
        version = archive.get("version")
        if type(version) is not int or version not in SUPPORTED_RECOVERY_ARCHIVE_VERSIONS:
            raise DurableSwarmError(
                "swarm recovery archive version disagrees with the runtime contract"
            )
        return self.store.checkpoint(
            run_id,
            archive,
            worker_id=worker_id,
            after_step_id=after_step_id,
            state_version=version,
        )

    def capture(
        self,
        run_id: str,
        worker_id: str,
        manager: SwarmRecoveryManager,
        runtime: SwarmRuntime,
        *,
        tenant_broker: TenantSwarmBroker | None = None,
        after_step_id: str | None = None,
    ) -> DurableSwarmCapture:
        """Capture swarm state and durably commit it as one logical operation.

        If durable persistence fails, the just-created in-memory swarm/tenant
        checkpoint is discarded. Older retained recovery history is untouched.
        """
        if not isinstance(manager, SwarmRecoveryManager):
            raise TypeError("manager must be a SwarmRecoveryManager")
        if not isinstance(runtime, SwarmRuntime):
            raise TypeError("runtime must be a SwarmRuntime")
        if tenant_broker is not None and not isinstance(tenant_broker, TenantSwarmBroker):
            raise TypeError("tenant_broker must be a TenantSwarmBroker or None")

        # Keep old retained snapshots even when an append evicts a ring entry.
        # Hold the owner locks across storage publication, not model execution.
        from contextlib import nullcontext
        tenant_lock = tenant_broker._lock if tenant_broker is not None else nullcontext()
        runtime_lock = getattr(runtime, "_lock", None) or nullcontext()
        with tenant_lock, runtime_lock, manager._lock:
            prior_runtime = manager.store.history()
            prior_tenants = manager.tenant_store.history()
            sequence = manager.checkpoint(runtime, tenant_broker)
            try:
                checkpoint = self.persist(
                    run_id, worker_id, manager, after_step_id=after_step_id,
                )
            except Exception:
                with manager.store._lock, manager.tenant_store._lock:
                    manager.store._items.clear()
                    manager.store._items.extend(prior_runtime)
                    manager.tenant_store._items.clear()
                    manager.tenant_store._items.extend(prior_tenants)
                raise
            return DurableSwarmCapture(sequence, checkpoint)

    def lease_and_capture_verified(self, run_id: str, worker_id: str,
                                   manager: SwarmRecoveryManager,
                                   tenant_broker: TenantSwarmBroker,
                                   candidates: tuple, *, now_ms: int
                                   ) -> tuple[str, SwarmTask, DurableSwarmCapture] | None:
        """Trusted owner boundary: commit the lease before returning its token.

        The existing durable run store must already own the exclusive run
        writer lease. No independent distributed writer election is supplied.
        If storage or its acknowledgement is uncertain, retire this broker
        generation and retain the task's worker and tenant custody; never
        publish the lease to a worker or automatically replay the task.
        """
        if not tenant_broker.verified_mode:
            raise DurableSwarmError("verified tenant custody required")
        runtime = tenant_broker.broker.runtime
        with tenant_broker._lock, runtime._lock, manager._lock:
            tenant_broker._assert_verified()
            selected = tenant_broker.lease_ranked_verified(candidates, now_ms=now_ms)
            if selected is None:
                return None
            tenant, task = selected
            try:
                capture = self.capture(run_id, worker_id, manager, runtime,
                                       tenant_broker=tenant_broker)
                latest = self.store.resume_state(run_id).checkpoint
                if (latest is None or latest.state_version != capture.checkpoint.state_version
                        or manager._json_bytes(latest.state) != manager._json_bytes(capture.checkpoint.state)
                        or manager._json_bytes(latest.state) != manager._json_bytes(manager.export_archive())):
                    raise DurableSwarmError("durable attempt publication readback mismatch")
            except Exception as exc:
                resident = runtime.task(task.id)
                if resident is not None and resident.state is TaskState.LEASED:
                    runtime._hold_uncertain(resident, reason="durable dispatch acknowledgement uncertain")
                tenant_broker.retire()
                raise DurableSwarmError("verified dispatch stopped; reconcile durable custody") from exc
            return tenant, task, capture

    def _capture_checked(self, run_id: str, worker_id: str, manager: SwarmRecoveryManager,
                         broker: TenantSwarmBroker) -> DurableSwarmCapture:
        capture = self.capture(run_id, worker_id, manager, broker.broker.runtime,
                               tenant_broker=broker)
        latest = self.store.resume_state(run_id).checkpoint
        if (latest is None or latest.state_version != capture.checkpoint.state_version
                or manager._json_bytes(latest.state) != manager._json_bytes(capture.checkpoint.state)
                or manager._json_bytes(latest.state) != manager._json_bytes(manager.export_archive())):
            raise DurableSwarmError("durable publication readback mismatch")
        return capture

    def submit_unique_verified(self, run_id: str, worker_id: str,
                               manager: SwarmRecoveryManager, broker: TenantSwarmBroker,
                               tenant: str, task: SwarmTask, *,
                               singleton_key: str | None = None) -> DurableSwarmCapture | None:
        """Persist an admitted unique job before returning acknowledgement.

        The existing tenant task identity is the idempotency key. Replay may
        checkpoint the same resident again, but cannot create a second job.
        The host holds the exclusive run writer and must restore the latest
        archive after any ambiguous acknowledgement. Direct bypass is outside
        the verified owner contract.
        """
        runtime = broker.broker.runtime
        with broker._lock, runtime._lock, manager._lock:
            broker._assert_verified()
            try:
                result = broker.submit_verified_queued(tenant, task, singleton_key=singleton_key)
                if not result.admitted:
                    return None
                return self._capture_checked(run_id, worker_id, manager, broker)
            except Exception as exc:
                # Even an exception on submission may have occurred after a
                # mutation. Never continue dispatch from an ambiguous owner.
                broker.retire()
                raise DurableSwarmError("unique job publication stopped; restore durable custody") from exc

    def wake_and_capture_verified(self, run_id: str, worker_id: str,
                                  manager: SwarmRecoveryManager, broker: TenantSwarmBroker,
                                  tenant: str, task_id: str, *, intent_sha256: str,
                                  receipt_sha256: str,
                                  verify_wake: Callable[[str, str, str, str], bool]) -> DurableSwarmCapture:
        """Persist one verified event/timeout receipt before allowing a dependent lease.

        The verifier independently authenticates the exact registered wait,
        event or trusted clock evidence. External transport/timer delivery is
        not provided here. The existing run writer must own the mutation.
        """
        tenant, task_id = broker._tenant(tenant), broker._task_id(task_id)
        if not callable(verify_wake) or any(type(v) is not str or len(v) != 64
                or any(c not in "0123456789abcdef" for c in v)
                for v in (intent_sha256, receipt_sha256)):
            raise DurableSwarmError("invalid wake evidence")
        runtime = broker.broker.runtime
        if verify_wake(tenant, task_id, intent_sha256, receipt_sha256) is not True:
            raise DurableSwarmError("wake evidence refused")
        with broker._lock, runtime._lock, manager._lock:
            broker._assert_verified()
            task = broker._verified_resident(tenant, task_id)
            if task.wait_intent_sha256 != intent_sha256:
                raise DurableSwarmError("wait identity changed")
            if task.wake_receipt_sha256 not in (None, receipt_sha256):
                raise DurableSwarmError("conflicting wake receipt")
            if task.wake_receipt_sha256 is None and (task.state is not TaskState.QUEUED or task.attempts):
                raise DurableSwarmError("wait is not eligible")
            try:
                runtime.open_wait(task_id, intent_sha256=intent_sha256, receipt_sha256=receipt_sha256)
                return self._capture_checked(run_id, worker_id, manager, broker)
            except Exception as exc:
                broker.retire()
                raise DurableSwarmError("wake publication stopped; restore durable custody") from exc

    def reconcile_and_enqueue_verified(self, run_id: str, worker_id: str,
                                       manager: SwarmRecoveryManager, broker: TenantSwarmBroker,
                                       tenant: str, parent_id: str, parent_worker: str, *,
                                       lease_token: str, evidence_sha256: str,
                                       followups: tuple[SwarmTask, ...],
                                       continuation_evidence_sha256: str | None = None
                                       ) -> DurableSwarmCapture:
        """Commit an uncertain parent's verified success and queued children together.

        Child admission happens while the parent still holds its dependency
        barrier. The existing checkpoint store publishes one complete archive
        after reconciliation. If any mutation or write is ambiguous, retire
        the generation without returning success; recovery uses the actual
        durable archive, never the partially mutated in-memory generation.
        This is atomic archive visibility, not a transaction with external
        effects or an independent outbox service.
        """
        from hashlib import sha256
        import json

        if (type(followups) is not tuple or not 1 <= len(followups) <= 64
                or any(not isinstance(t, SwarmTask) for t in followups)):
            raise DurableSwarmError("invalid follow-up batch")
        if len({t.id for t in followups}) != len(followups):
            raise DurableSwarmError("duplicate follow-up identity")
        manifest = []
        for task in followups:
            if (task.dependencies != (parent_id,) or task.id == parent_id
                    or task.state is not TaskState.QUEUED or task.attempts or task.effect_uncertain
                    or task.lease_token is not None or task.leased_to is not None
                    or task.lease_deadline is not None or task.reconciliation_sha256 is not None
                    or task.wait_intent_sha256 is not None or task.wake_receipt_sha256 is not None
                    or task.singleton_scope_sha256 is not None):
                raise DurableSwarmError("follow-up must be fresh and depend only on parent")
            manifest.append([task.id, dict(task.payload), task.priority, task.max_attempts,
                             sorted(task.required_capabilities), task.dependencies])
        encoded = json.dumps([run_id, tenant, parent_id, manifest], sort_keys=True,
                             separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        if len(encoded) > 1024 * 1024:
            raise DurableSwarmError("follow-up manifest exceeds bound")
        pin = sha256(encoded).hexdigest()
        runtime = broker.broker.runtime
        with broker._lock, broker.broker._completion_lock, runtime._lock, manager._lock:
            broker._assert_verified()
            parent = broker._verified_resident(tenant, parent_id)
            if not parent.effect_uncertain or parent.leased_to != parent_worker or parent.lease_token != lease_token:
                raise DurableSwarmError("parent uncertain attempt does not match")
            # Trusted host must independently authorize the exact continuation
            # manifest in addition to the parent's actual outcome evidence.
            broker.broker._verified(parent_worker, parent_id, lease_token,
                                    "enqueue:" + pin, continuation_evidence_sha256
                                    if continuation_evidence_sha256 is not None else evidence_sha256)
            broker.broker._verified(parent_worker, parent_id, lease_token,
                                    "reconcile:committed", evidence_sha256)
            for task in followups:
                if (broker.tenant_for(task.id) is not None or runtime.task(task.id) is not None):
                    raise DurableSwarmError("follow-up identity already resident")
            try:
                for task in followups:
                    decision = broker.submit_verified_queued(tenant, task)
                    if not decision.admitted or decision.duplicate:
                        raise DurableSwarmError("follow-up admission refused")
                broker.reconcile_verified(tenant, parent_worker, parent_id,
                                          lease_token=lease_token, outcome="committed",
                                          evidence_sha256=evidence_sha256)
                return self._capture_checked(run_id, worker_id, manager, broker)
            except Exception as exc:
                broker.retire()
                raise DurableSwarmError("completion and enqueue stopped; restore durable custody") from exc


    def finish_and_capture_verified(
        self, run_id: str, owner_id: str, manager: SwarmRecoveryManager,
        broker: TenantSwarmBroker, tenant: str, task_id: str, *,
        worker_id: str, lease_token: str, outcome: str,
        evidence_sha256: str,
    ) -> tuple[SwarmTask, DurableSwarmCapture]:
        """Publish a normal outcome only after durable readback.

        A transport must not acknowledge an attempt until this returns. On
        ambiguous publication restore the authoritative archive, never retry
        the physical effect. The host continues to own the run-writer lease.
        """
        if outcome not in ("success", "uncertain"):
            raise DurableSwarmError("unsupported verified outcome")
        tenant, task_id = broker._tenant(tenant), broker._task_id(task_id)
        runtime = broker.broker.runtime
        with broker._lock, broker.broker._completion_lock, runtime._lock, manager._lock:
            resident = broker._verified_resident(tenant, task_id)
            if (resident.state is not TaskState.LEASED or resident.effect_uncertain
                    or resident.leased_to != worker_id or resident.lease_token != lease_token):
                raise DurableSwarmError("active attempt identity changed")
            try:
                result = broker.record_verified(
                    tenant, worker_id, task_id, lease_token=lease_token,
                    outcome=outcome, evidence_sha256=evidence_sha256,
                )
                return result.task, self._capture_checked(run_id, owner_id, manager, broker)
            except Exception as exc:
                broker.retire()
                raise DurableSwarmError("completion publication stopped; restore durable custody") from exc

    def reconcile_and_capture_verified(
        self, run_id: str, owner_id: str, manager: SwarmRecoveryManager,
        broker: TenantSwarmBroker, tenant: str, task_id: str, *,
        worker_id: str, lease_token: str, outcome: str,
        evidence_sha256: str,
    ) -> tuple[SwarmTask, DurableSwarmCapture]:
        """Commit independently verified reconciliation before releasing custody."""
        if outcome not in ("committed", "stopped-no-effect", "stopped-terminal"):
            raise DurableSwarmError("unsupported reconciliation outcome")
        tenant, task_id = broker._tenant(tenant), broker._task_id(task_id)
        runtime = broker.broker.runtime
        with broker._lock, broker.broker._completion_lock, runtime._lock, manager._lock:
            resident = broker._verified_resident(tenant, task_id)
            if (not resident.effect_uncertain or resident.leased_to != worker_id
                    or resident.lease_token != lease_token):
                raise DurableSwarmError("uncertain attempt identity changed")
            try:
                result = broker.reconcile_verified(
                    tenant, worker_id, task_id, lease_token=lease_token,
                    outcome=outcome, evidence_sha256=evidence_sha256,
                )
                return result.task, self._capture_checked(run_id, owner_id, manager, broker)
            except Exception as exc:
                broker.retire()
                raise DurableSwarmError("reconciliation stopped; restore durable custody") from exc



    def hold_transport_unknown(
        self, run_id: str, owner_id: str, manager: SwarmRecoveryManager,
        broker: TenantSwarmBroker, tenant: str, task_id: str, *,
        worker_id: str, lease_token: str,
    ) -> tuple[SwarmTask, DurableSwarmCapture]:
        """A failed handoff is not evidence that the physical effect stopped.

        Even when a transport supplies no authenticated response, the trusted
        owner can conservatively preserve capacity and exact attempt custody.
        This path never returns successful completion or permits retry.
        """
        tenant, task_id = broker._tenant(tenant), broker._task_id(task_id)
        runtime = broker.broker.runtime
        with broker._lock, broker.broker._completion_lock, runtime._lock, manager._lock:
            resident = broker._verified_resident(tenant, task_id)
            if (not runtime.fenced or resident.leased_to != worker_id
                    or resident.lease_token != lease_token
                    or broker.ingress.phase(tenant, task_id) != "leased"
                    or (resident.state is not TaskState.LEASED and not resident.effect_uncertain)):
                raise DurableSwarmError("transport attempt custody changed")
            try:
                if not resident.effect_uncertain:
                    resident = runtime._hold_uncertain(
                        resident, reason="transport acknowledgement uncertain",
                    )
                return resident, self._capture_checked(run_id, owner_id, manager, broker)
            except Exception as exc:
                broker.retire()
                raise DurableSwarmError("transport custody uncertain; restore durable archive") from exc


    def load(self, run_id: str) -> DurableSwarmRecovery | None:
        """Load and verify the latest durable swarm archive for an outer run."""
        resume = self.store.resume_state(run_id)
        checkpoint = resume.checkpoint
        if checkpoint is None:
            return None
        if checkpoint.state_version not in SUPPORTED_RECOVERY_ARCHIVE_VERSIONS:
            raise DurableSwarmError(
                "unsupported durable swarm checkpoint state version: "
                f"{checkpoint.state_version}"
            )
        if not isinstance(checkpoint.state, dict):
            raise DurableSwarmError("durable swarm checkpoint must contain an object")
        archive_version = checkpoint.state.get("version")
        if archive_version != checkpoint.state_version:
            raise DurableSwarmError("durable checkpoint envelope/archive version mismatch")
        try:
            manager = SwarmRecoveryManager.from_archive(checkpoint.state)
        except (TypeError, ValueError) as exc:
            raise DurableSwarmError("invalid durable swarm recovery archive") from exc
        return DurableSwarmRecovery(
            manager=manager,
            checkpoint=checkpoint,
            resume=resume,
        )

    def restore_runtime(self, run_id: str):
        """Restore the latest swarm runtime, or ``None`` when no archive exists."""
        recovery = self.load(run_id)
        return None if recovery is None else recovery.restore_runtime()

# Host-owned wait protocol. Raw task payloads never supply signing keys or clock
# authority. The reserved envelope is stored in the existing task checkpoint.
_HOST_WAIT_FIELD = "_jeeves_host_wait_v1"
_MAX_WAIT_MS = (1 << 53) - 1


def _wait_identifier(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 256
            or value != value.strip()
            or any(ord(char) < 33 or ord(char) > 126 for char in value)):
        raise DurableSwarmError("invalid host wait identifier")
    return value


def _wait_time(value: int) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_WAIT_MS:
        raise DurableSwarmError("invalid host wait timestamp")
    return value


def _wait_digest(value: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise DurableSwarmError("invalid host wait digest")
    return value


def _wait_bytes(value: object) -> bytes:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _wait_hash(value: object) -> str:
    from hashlib import sha256
    return sha256(_wait_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class HostWaitIntent:
    """Exact run/tenant/task-bound event or UTC timer intent."""

    run_id: str
    tenant: str
    task_id: str
    kind: str
    source: str
    selector: str
    not_before_ms: int
    expires_ms: int | None = None

    def __post_init__(self) -> None:
        for value in (self.run_id, self.tenant, self.task_id, self.source, self.selector):
            _wait_identifier(value)
        if self.kind not in ("timer", "event"):
            raise DurableSwarmError("invalid host wait kind")
        if self.kind == "timer" and (self.source != "host-clock" or self.selector != "deadline"
                                     or self.expires_ms is not None):
            raise DurableSwarmError("invalid timer intent")
        _wait_time(self.not_before_ms)
        if self.expires_ms is not None and _wait_time(self.expires_ms) < self.not_before_ms:
            raise DurableSwarmError("invalid event window")

    def record(self) -> dict[str, object]:
        return {
            "run_id": self.run_id, "tenant": self.tenant, "task_id": self.task_id,
            "kind": self.kind, "source": self.source, "selector": self.selector,
            "not_before_ms": self.not_before_ms, "expires_ms": self.expires_ms,
        }

    @property
    def digest(self) -> str:
        return _wait_hash(["jeeves-host-wait-v1", self.record()])

    @classmethod
    def from_record(cls, record: object) -> HostWaitIntent:
        if type(record) is not dict or set(record) != {
            "run_id", "tenant", "task_id", "kind", "source", "selector",
            "not_before_ms", "expires_ms",
        }:
            raise DurableSwarmError("invalid pinned host wait envelope")
        return cls(**record)


@dataclass(frozen=True, slots=True)
class HostEventReceipt:
    """Source-authenticated event evidence; the transport retains its envelope."""

    intent_sha256: str
    event_id: str
    evidence_sha256: str
    observed_ms: int
    signature_sha256: str

    def __post_init__(self) -> None:
        _wait_digest(self.intent_sha256)
        _wait_identifier(self.event_id)
        _wait_digest(self.evidence_sha256)
        _wait_time(self.observed_ms)
        _wait_digest(self.signature_sha256)

    def signed_fields(self) -> list[object]:
        return ["jeeves-host-event-v1", self.intent_sha256, self.event_id,
                self.evidence_sha256, self.observed_ms]

    @property
    def digest(self) -> str:
        return _wait_hash([self.signed_fields(), self.signature_sha256])

    @classmethod
    def issue(cls, intent: HostWaitIntent, *, event_id: str, evidence_sha256: str,
              observed_ms: int, source_key: bytes) -> HostEventReceipt:
        """For trusted event collectors with the independently provisioned key."""
        import hmac
        if intent.kind != "event":
            raise DurableSwarmError("not an event intent")
        _validate_wait_key(source_key)
        unsigned = cls(intent.digest, event_id, evidence_sha256, observed_ms, "0" * 64)
        signature = hmac.digest(source_key, _wait_bytes(unsigned.signed_fields()),
                                "sha256").hex()
        return cls(intent.digest, event_id, evidence_sha256, observed_ms, signature)


def _validate_wait_key(key: bytes) -> None:
    if type(key) is not bytes or not 32 <= len(key) <= 128:
        raise DurableSwarmError("invalid host event key")


class HostWaitDriver:
    """Trusted local run-owner handler for event delivery and restart-safe timers.

    Invoke poll_due_timers from the host's existing service loop. No hidden
    thread, external webhook endpoint, clock synchronization or key storage is
    created. Key provisioning belongs to the trusted host, not a task.
    """

    def __init__(
        self, bridge: SwarmDurableBridge, run_id: str, owner_id: str,
        manager: SwarmRecoveryManager, broker: TenantSwarmBroker, *,
        source_keys: dict[tuple[str, str], bytes],
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        from time import time_ns
        self.bridge = bridge
        self.run_id = _wait_identifier(run_id)
        self.owner_id = _wait_identifier(owner_id)
        self.manager = manager
        self.broker = broker
        broker._assert_verified()
        if type(source_keys) is not dict or len(source_keys) > 4096:
            raise DurableSwarmError("invalid event source registry")
        self._source_keys: dict[tuple[str, str], bytes] = {}
        for scope, key in source_keys.items():
            if type(scope) is not tuple or len(scope) != 2:
                raise DurableSwarmError("invalid event source scope")
            tenant, source = scope
            _validate_wait_key(key)
            self._source_keys[(_wait_identifier(tenant), _wait_identifier(source))] = key
        if clock_ms is not None and not callable(clock_ms):
            raise DurableSwarmError("invalid host clock")
        self._clock_ms = clock_ms if clock_ms is not None else lambda: time_ns() // 1_000_000

    def _now(self) -> int:
        return _wait_time(self._clock_ms())

    def submit(self, intent: HostWaitIntent, task: SwarmTask, *,
               singleton_key: str | None = None) -> DurableSwarmCapture | None:
        from dataclasses import replace
        if (not isinstance(intent, HostWaitIntent) or not isinstance(task, SwarmTask)
                or intent.run_id != self.run_id or intent.task_id != task.id
                or task.wait_intent_sha256 is not None or task.wake_receipt_sha256 is not None
                or _HOST_WAIT_FIELD in task.payload):
            raise DurableSwarmError("host wait submission identity mismatch")
        if intent.kind == "event" and (intent.tenant, intent.source) not in self._source_keys:
            raise DurableSwarmError("event source unavailable for tenant")
        payload = dict(task.payload)
        payload[_HOST_WAIT_FIELD] = intent.record()
        prepared = replace(task, payload=payload, wait_intent_sha256=intent.digest)
        return self.bridge.submit_unique_verified(
            self.run_id, self.owner_id, self.manager, self.broker,
            intent.tenant, prepared, singleton_key=singleton_key,
        )

    def _read(self, tenant: str, task_id: str) -> tuple[HostWaitIntent, SwarmTask]:
        task = self.broker._verified_resident(tenant, task_id)
        intent = HostWaitIntent.from_record(task.payload.get(_HOST_WAIT_FIELD))
        if (intent.run_id != self.run_id or intent.tenant != tenant
                or intent.task_id != task_id or intent.digest != task.wait_intent_sha256):
            raise DurableSwarmError("persisted host wait identity mismatch")
        return intent, task

    def _publish(self, intent: HostWaitIntent, receipt_sha256: str) -> DurableSwarmCapture:
        # The authenticated decision is exact to the four bridge callback
        # arguments. Neither caller payload nor any other task can reuse it.
        identity = (intent.tenant, intent.task_id, intent.digest, receipt_sha256)
        return self.bridge.wake_and_capture_verified(
            self.run_id, self.owner_id, self.manager, self.broker,
            intent.tenant, intent.task_id, intent_sha256=intent.digest,
            receipt_sha256=receipt_sha256,
            verify_wake=lambda *values: values == identity,
        )

    def deliver_event(self, tenant: str, task_id: str,
                      receipt: HostEventReceipt) -> DurableSwarmCapture:
        import hmac
        if not isinstance(receipt, HostEventReceipt):
            raise DurableSwarmError("invalid event receipt")
        runtime = self.broker.broker.runtime
        with self.broker._lock, runtime._lock:
            intent, task = self._read(tenant, task_id)
            key = self._source_keys.get((tenant, intent.source))
            if intent.kind != "event" or key is None or receipt.intent_sha256 != intent.digest:
                raise DurableSwarmError("event source or wait identity refused")
            expected = hmac.digest(key, _wait_bytes(receipt.signed_fields()), "sha256").hex()
            if not hmac.compare_digest(expected, receipt.signature_sha256):
                raise DurableSwarmError("event signature refused")
            now = self._now()
            if (receipt.observed_ms < intent.not_before_ms or receipt.observed_ms > now
                    or (intent.expires_ms is not None and receipt.observed_ms > intent.expires_ms)):
                raise DurableSwarmError("event observation outside registered window")
            if task.wake_receipt_sha256 not in (None, receipt.digest):
                raise DurableSwarmError("conflicting event receipt")
            return self._publish(intent, receipt.digest)

    def poll_due_timers(self, *, limit: int = 64) -> tuple[str, ...]:
        """Wake up to limit due tasks, each with checkpoint/readback before return.

        The durable task list is the timer source of truth, so a restarted host
        can resume without an auxiliary timer database. Missed ticks do not
        discard due timers. UTC clock accuracy is the host's responsibility.
        """
        if type(limit) is not int or not 1 <= limit <= 1024:
            raise DurableSwarmError("invalid timer batch bound")
        runtime = self.broker.broker.runtime
        with self.broker._lock, runtime._lock:
            self.broker._assert_verified()
            now = self._now()
            due: list[HostWaitIntent] = []
            for task in runtime.tasks():
                if (task.state is not TaskState.QUEUED or task.attempts
                        or task.wake_receipt_sha256 is not None
                        or _HOST_WAIT_FIELD not in task.payload):
                    continue
                tenant = self.broker.tenant_for(task.id)
                if tenant is None:
                    raise DurableSwarmError("unowned timer candidate")
                intent, _ = self._read(tenant, task.id)
                if intent.kind == "timer" and intent.not_before_ms <= now:
                    due.append(intent)
            due.sort(key=lambda intent: (intent.not_before_ms, intent.tenant, intent.task_id))
            published: list[str] = []
            for intent in due[:limit]:
                # Deterministic receipt identity across clock ticks and restarts.
                # Recheck the trusted clock to fail closed on a backwards sample.
                if self._now() < intent.not_before_ms:
                    break
                receipt = _wait_hash(["jeeves-host-timer-v1", intent.digest, intent.not_before_ms])
                self._publish(intent, receipt)
                published.append(intent.task_id)
            return tuple(published)

# Worker evidence must authenticate both the exact attempt and its evidence
# bytes. A reconciliation issuer may be independent of the original worker.
_WORKER_ACTIONS = frozenset({
    "success", "uncertain", "reconcile:committed",
    "reconcile:stopped-no-effect", "reconcile:stopped-terminal", "enqueue",
})


def _worker_action(value: str) -> str:
    if type(value) is not str:
        raise DurableSwarmError("invalid worker receipt action")
    if value in _WORKER_ACTIONS and value != "enqueue":
        return value
    if value.startswith("enqueue:"):
        _wait_digest(value[8:])
        return "enqueue"
    raise DurableSwarmError("invalid worker receipt action")


@dataclass(frozen=True, slots=True)
class HostWorkerReceipt:
    """Authenticated immutable worker/reconciler evidence envelope."""

    run_id: str
    issuer: str
    worker_id: str
    task_id: str
    lease_token: str
    action: str
    artifact_sha256: str
    signature_sha256: str

    def __post_init__(self) -> None:
        for value in (self.run_id, self.issuer, self.worker_id, self.task_id):
            _wait_identifier(value)
        if (type(self.lease_token) is not str or len(self.lease_token) != 32
                or any(char not in "0123456789abcdef" for char in self.lease_token)):
            raise DurableSwarmError("invalid worker receipt attempt token")
        _worker_action(self.action)
        _wait_digest(self.artifact_sha256)
        _wait_digest(self.signature_sha256)

    def signed_fields(self) -> list[object]:
        return ["jeeves-host-worker-v1", self.run_id, self.issuer, self.worker_id,
                self.task_id, self.lease_token, self.action, self.artifact_sha256]

    @property
    def digest(self) -> str:
        return _wait_hash([self.signed_fields(), self.signature_sha256])

    @classmethod
    def issue(cls, *, run_id: str, issuer: str, worker_id: str, task_id: str,
              lease_token: str, action: str, artifact_sha256: str,
              issuer_key: bytes) -> HostWorkerReceipt:
        import hmac
        from dataclasses import replace
        _validate_wait_key(issuer_key)
        unsigned = cls(run_id, issuer, worker_id, task_id, lease_token, action,
                       artifact_sha256, "0" * 64)
        signature = hmac.digest(issuer_key, _wait_bytes(unsigned.signed_fields()),
                                "sha256").hex()
        return replace(unsigned, signature_sha256=signature)


class HostWorkerAuthority:
    """Callable verifier for the canonical SwarmBroker verify_worker seam.

    Trusted host configuration supplies distinct issuer/worker/action grants,
    a receipt resolver and an independent evidence-content validator. The
    resolver supplies exact receipt AND artifact bytes from host custody.
    No digest, signature, or worker assertion alone proves a physical effect.
    The caller must keep receipts available after restart and provision
    reconciliation grants separately from ordinary worker grants.
    """

    def __init__(
        self, run_id: str, *,
        grants: dict[tuple[str, str], tuple[bytes, frozenset[str]]],
        resolve: Callable[[str], tuple[HostWorkerReceipt, bytes] | None],
        validate_evidence: Callable[[HostWorkerReceipt, bytes], bool],
        max_artifact_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        self.run_id = _wait_identifier(run_id)
        if (type(grants) is not dict or len(grants) > 10000
                or not callable(resolve) or not callable(validate_evidence)
                or type(max_artifact_bytes) is not int
                or not 1 <= max_artifact_bytes <= 64 * 1024 * 1024):
            raise DurableSwarmError("invalid worker evidence authority")
        self._grants: dict[tuple[str, str], tuple[bytes, frozenset[str]]] = {}
        issuer_roles: dict[str, bool] = {}
        key_owners: dict[bytes, str] = {}
        for scope, grant in grants.items():
            if (type(scope) is not tuple or len(scope) != 2
                    or type(grant) is not tuple or len(grant) != 2):
                raise DurableSwarmError("invalid worker issuer scope")
            issuer, worker_id = scope
            key, actions = grant
            _validate_wait_key(key)
            if (type(actions) is not frozenset or not actions
                    or not actions.issubset(_WORKER_ACTIONS)):
                raise DurableSwarmError("invalid worker issuer action grant")
            # Distinct effect and reconciliation roles per issuer. A worker
            # with a completion credential cannot promote its own uncertainty.
            if (actions & {"success", "uncertain"}
                    and actions - {"success", "uncertain"}):
                raise DurableSwarmError("worker and reconciler grants must be separate")
            issuer, worker_id = _wait_identifier(issuer), _wait_identifier(worker_id)
            effect_role = bool(actions & {"success", "uncertain"})
            if (issuer_roles.get(issuer, effect_role) != effect_role
                    or key_owners.get(key, issuer) != issuer):
                raise DurableSwarmError("worker issuer roles and credentials must be independent")
            issuer_roles[issuer] = effect_role
            key_owners[key] = issuer
            self._grants[(issuer, worker_id)] = (key, actions)
        self._resolve = resolve
        self._validate_evidence = validate_evidence
        self._max_artifact_bytes = max_artifact_bytes

    def __call__(self, worker_id: str, task_id: str, lease_token: str,
                 action: str, evidence_sha256: str) -> bool:
        import hmac
        from hashlib import sha256
        try:
            action_scope = _worker_action(action)
            _wait_digest(evidence_sha256)
            bundle = self._resolve(evidence_sha256)
            if type(bundle) is not tuple or len(bundle) != 2:
                return False
            receipt, artifact = bundle
            if (type(receipt) is not HostWorkerReceipt or type(artifact) is not bytes
                    or len(artifact) > self._max_artifact_bytes
                    or (receipt.run_id, receipt.worker_id, receipt.task_id,
                        receipt.lease_token, receipt.action) !=
                       (self.run_id, worker_id, task_id, lease_token, action)
                    or not hmac.compare_digest(receipt.digest, evidence_sha256)):
                return False
            grant = self._grants.get((receipt.issuer, worker_id))
            if grant is None or action_scope not in grant[1]:
                return False
            expected = hmac.digest(grant[0], _wait_bytes(receipt.signed_fields()),
                                   "sha256").hex()
            if (not hmac.compare_digest(expected, receipt.signature_sha256)
                    or not hmac.compare_digest(sha256(artifact).hexdigest(),
                                               receipt.artifact_sha256)):
                return False
            return self._validate_evidence(receipt, artifact) is True
        except Exception:
            # Malformed evidence, unavailable custody or a failing independent
            # validator may never open a verified execution boundary.
            return False

@dataclass(frozen=True, slots=True)
class HostDispatchAttempt:
    """Immutable transport handoff created only after durable lease readback."""

    run_id: str
    tenant: str
    task_id: str
    worker_id: str
    lease_token: str
    payload_json: bytes

    def payload(self) -> dict[str, object]:
        import json
        # Transport receives an independent copy; never the resident map.
        return json.loads(self.payload_json)


@dataclass(frozen=True, slots=True)
class HostTransportReply:
    outcome: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if self.outcome not in ("success", "uncertain"):
            raise DurableSwarmError("invalid transport outcome")
        _wait_digest(self.evidence_sha256)


@dataclass(frozen=True, slots=True)
class HostDispatchCycle:
    timers_woken: tuple[str, ...]
    task_id: str | None
    disposition: str
    evidence_sha256: str | None = None


class HostDispatchService:
    """Local trusted owner execution loop over the canonical dispatch path.

    A cycle wakes due timers, publishes at most one exact authorized lease,
    calls the host-owned transport once, verifies its receipt and commits an
    outcome. No runtime/broker locks are held while the transport executes.
    The supplied transport is responsible for its own bounded I/O, actual
    worker launch/cancellation, durable receipt custody and independent
    evidence publication. This service never starts hidden threads or grants
    model-generated tasks authority. The outer host must hold its run lease.
    """

    def __init__(self, wait_driver: HostWaitDriver, *,
                 transport: Callable[[HostDispatchAttempt], HostTransportReply]) -> None:
        from threading import Lock
        if not isinstance(wait_driver, HostWaitDriver) or not callable(transport):
            raise DurableSwarmError("invalid host dispatch service configuration")
        authority = wait_driver.broker.broker._verify_worker
        if not isinstance(authority, HostWorkerAuthority) or authority.run_id != wait_driver.run_id:
            raise DurableSwarmError("host dispatch requires run-bound worker evidence authority")
        self.wait_driver = wait_driver
        self._transport = transport
        self._cycle_lock = Lock()

    def cycle(self, candidates: tuple, *, now_ms: int,
              timer_limit: int = 64) -> HostDispatchCycle:
        from skeleton.intelligence.dispatch_policy import DispatchCandidate, bounded_int, MAX_CANDIDATES
        if (type(candidates) is not tuple or len(candidates) > MAX_CANDIDATES
                or any(not isinstance(candidate, DispatchCandidate) for candidate in candidates)):
            raise DurableSwarmError("invalid authorized dispatch candidate batch")
        bounded_int(now_ms, "dispatch time")
        if not self._cycle_lock.acquire(blocking=False):
            raise DurableSwarmError("host dispatch cycle already active")
        try:
            owner = self.wait_driver
            timers = owner.poll_due_timers(limit=timer_limit)
            selection = owner.bridge.lease_and_capture_verified(
                owner.run_id, owner.owner_id, owner.manager, owner.broker,
                candidates, now_ms=now_ms,
            )
            if selection is None:
                return HostDispatchCycle(timers, None, "idle")
            tenant, task, _capture = selection
            # This is an owned lease returned after checkpoint/readback. Any
            # preparation or transport error must retain the original attempt.
            if task.leased_to is None or task.lease_token is None:
                owner.broker.retire()
                raise DurableSwarmError("durable attempt missing its transport identity")
            try:
                payload = dict(task.payload)
                payload.pop(_HOST_WAIT_FIELD, None)
                attempt = HostDispatchAttempt(
                    owner.run_id, tenant, task.id, task.leased_to, task.lease_token,
                    _wait_bytes(payload),
                )
                reply = self._transport(attempt)
                if type(reply) is not HostTransportReply:
                    raise DurableSwarmError("transport did not return an evidence receipt")
            except Exception:
                owner.bridge.hold_transport_unknown(
                    owner.run_id, owner.owner_id, owner.manager, owner.broker,
                    tenant, task.id, worker_id=task.leased_to,
                    lease_token=task.lease_token,
                )
                return HostDispatchCycle(timers, task.id, "transport-unknown")
            # Invalid/expired evidence or ambiguous storage acknowledgement
            # causes finish_and_capture_verified to retire the owner. Restore
            # from the durable pre-execution archive; never re-call transport.
            result, _ = owner.bridge.finish_and_capture_verified(
                owner.run_id, owner.owner_id, owner.manager, owner.broker,
                tenant, task.id, worker_id=task.leased_to, lease_token=task.lease_token,
                outcome=reply.outcome, evidence_sha256=reply.evidence_sha256,
            )
            return HostDispatchCycle(
                timers, task.id,
                "uncertain" if result.effect_uncertain else "completed",
                reply.evidence_sha256,
            )
        finally:
            self._cycle_lock.release()

@dataclass(frozen=True, slots=True)
class LocalAttemptRecord:
    attempt: HostDispatchAttempt
    receipt_sha256: str | None


def _check_local_attempt(attempt: HostDispatchAttempt) -> None:
    import json
    if type(attempt) is not HostDispatchAttempt:
        raise DurableSwarmError("invalid local attempt")
    for value in (attempt.run_id, attempt.tenant, attempt.task_id, attempt.worker_id):
        _wait_identifier(value)
    if (type(attempt.lease_token) is not str or len(attempt.lease_token) != 32
            or any(char not in "0123456789abcdef" for char in attempt.lease_token)
            or type(attempt.payload_json) is not bytes
            or not 1 <= len(attempt.payload_json) <= 65536):
        raise DurableSwarmError("invalid local attempt payload or token")
    try:
        value = json.loads(attempt.payload_json)
        if type(value) is not dict or _wait_bytes(value) != attempt.payload_json:
            raise DurableSwarmError("noncanonical local attempt")
    except (ValueError, TypeError, RecursionError) as exc:
        raise DurableSwarmError("invalid local attempt JSON") from exc


class SQLiteWorkerCustody:
    """Bounded local evidence journal; not a second scheduler.

    The host supplies a dedicated private directory. SQLite serializes
    publication across processes. A committed start tombstone precedes
    physical execution and is never automatically removed or retried.
    Completed attempts atomically bind receipt and evidence bytes.
    """

    def __init__(self, directory, *, max_attempts: int = 10000,
                 max_bytes: int = 256 * 1024 * 1024,
                 max_artifact_bytes: int = 65536) -> None:
        import os
        import stat
        from pathlib import Path
        if (type(max_attempts) is not int or not 1 <= max_attempts <= 1_000_000
                or type(max_bytes) is not int or not 1024 <= max_bytes <= 64 * 1024**3
                or type(max_artifact_bytes) is not int
                or not 128 <= max_artifact_bytes <= min(max_bytes, 16 * 1024**2)):
            raise DurableSwarmError("invalid local custody capacity")
        root = Path(directory)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise DurableSwarmError("local custody requires a trusted absolute directory")
        root_stat = root.stat()
        if os.name == "posix" and (root_stat.st_uid != os.getuid() or root_stat.st_mode & 0o077):
            raise DurableSwarmError("local custody directory is not private")
        self.directory = root.resolve(strict=True)
        self.path = self.directory / "worker-custody.sqlite3"
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self._check_path()
        self.max_attempts = max_attempts
        self.max_bytes = max_bytes
        self.max_artifact_bytes = max_artifact_bytes
        from contextlib import closing
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise DurableSwarmError("unsupported worker custody schema")
                if version == 0:
                    existing = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    if existing:
                        raise DurableSwarmError("unrecognized worker custody database")
                    conn.execute("""
                        CREATE TABLE custody_limits (
                            id INTEGER PRIMARY KEY CHECK(id=1),
                            max_attempts INTEGER NOT NULL,
                            max_bytes INTEGER NOT NULL,
                            max_artifact_bytes INTEGER NOT NULL
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE attempts (
                            run_id TEXT NOT NULL, lease_token TEXT NOT NULL,
                            tenant TEXT NOT NULL, task_id TEXT NOT NULL,
                            worker_id TEXT NOT NULL, payload BLOB NOT NULL,
                            charge INTEGER NOT NULL CHECK(charge>0),
                            receipt_digest TEXT UNIQUE, receipt BLOB, artifact BLOB,
                            PRIMARY KEY (run_id, lease_token),
                            CHECK ((receipt_digest IS NULL AND receipt IS NULL AND artifact IS NULL)
                                OR (receipt_digest IS NOT NULL AND receipt IS NOT NULL
                                    AND artifact IS NOT NULL))
                        ) WITHOUT ROWID
                    """)
                    conn.execute("CREATE INDEX attempts_task ON attempts(run_id, task_id)")
                    conn.execute("INSERT INTO custody_limits VALUES (1,?,?,?)",
                                 (max_attempts, max_bytes, max_artifact_bytes))
                    conn.execute("PRAGMA user_version=1")
                limits = conn.execute(
                    "SELECT max_attempts,max_bytes,max_artifact_bytes FROM custody_limits WHERE id=1"
                ).fetchone()
                if limits != (max_attempts, max_bytes, max_artifact_bytes):
                    raise DurableSwarmError("worker custody capacity policy changed")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _check_path(self) -> None:
        import os
        import stat
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise DurableSwarmError("worker custody file must be a private regular file")
        if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise DurableSwarmError("worker custody file permissions refused")

    def _connect(self):
        import sqlite3
        self._check_path()
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA trusted_schema=OFF")
            return conn
        except BaseException:
            conn.close()
            raise

    def begin(self, attempt: HostDispatchAttempt) -> bool:
        """Reserve evidence capacity and write the start tombstone first.

        False means this token was already started, even if no outcome is
        known. Never launch again from False. Logical reservation is not
        a guarantee of available physical disk space.
        """
        from contextlib import closing
        _check_local_attempt(attempt)
        charge = len(attempt.payload_json) + self.max_artifact_bytes + 4096
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT tenant,task_id,worker_id,payload FROM attempts "
                    "WHERE run_id=? AND lease_token=?", (attempt.run_id, attempt.lease_token)
                ).fetchone()
                identity = (attempt.tenant, attempt.task_id, attempt.worker_id, attempt.payload_json)
                if row is not None:
                    if row != identity:
                        raise DurableSwarmError("attempt tombstone identity conflict")
                    conn.commit()
                    return False
                count, occupied = conn.execute(
                    "SELECT count(*),coalesce(sum(charge),0) FROM attempts"
                ).fetchone()
                if count >= self.max_attempts or occupied + charge > self.max_bytes:
                    raise DurableSwarmError("worker evidence custody capacity exhausted")
                conn.execute(
                    "INSERT INTO attempts(run_id,lease_token,tenant,task_id,worker_id,payload,charge)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (attempt.run_id, attempt.lease_token, *identity, charge),
                )
                conn.commit()
                return True
            except BaseException:
                conn.rollback()
                raise

    def finish(self, attempt: HostDispatchAttempt, receipt: HostWorkerReceipt,
               artifact: bytes) -> str:
        """Atomically publish the exact result; repeated identical writes are inert."""
        from contextlib import closing
        from dataclasses import asdict
        from hashlib import sha256
        _check_local_attempt(attempt)
        if (type(receipt) is not HostWorkerReceipt or type(artifact) is not bytes
                or not 1 <= len(artifact) <= self.max_artifact_bytes
                or (receipt.run_id, receipt.worker_id, receipt.task_id, receipt.lease_token)
                != (attempt.run_id, attempt.worker_id, attempt.task_id, attempt.lease_token)
                or receipt.action not in ("success", "uncertain")
                or sha256(artifact).hexdigest() != receipt.artifact_sha256):
            raise DurableSwarmError("worker result does not match its exact attempt")
        encoded = _wait_bytes(asdict(receipt))
        if len(encoded) > 4096:
            raise DurableSwarmError("worker receipt exceeds reservation")
        digest = receipt.digest
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT tenant,task_id,worker_id,payload,receipt_digest,receipt,artifact "
                    "FROM attempts WHERE run_id=? AND lease_token=?",
                    (attempt.run_id, attempt.lease_token),
                ).fetchone()
                if row is None or row[:4] != (
                        attempt.tenant, attempt.task_id, attempt.worker_id, attempt.payload_json):
                    raise DurableSwarmError("worker start custody missing or mismatched")
                if row[4] is not None:
                    if row[4:] != (digest, encoded, artifact):
                        raise DurableSwarmError("immutable worker result conflict")
                else:
                    conn.execute(
                        "UPDATE attempts SET receipt_digest=?,receipt=?,artifact=? "
                        "WHERE run_id=? AND lease_token=? AND receipt_digest IS NULL",
                        (digest, encoded, artifact, attempt.run_id, attempt.lease_token),
                    )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        if self.resolve(digest) != (receipt, artifact):
            raise DurableSwarmError("worker result readback mismatch")
        return digest

    def resolve(self, digest: str) -> tuple[HostWorkerReceipt, bytes] | None:
        from contextlib import closing
        from hashlib import sha256
        import json
        _wait_digest(digest)
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT run_id,lease_token,worker_id,task_id,receipt,artifact FROM attempts "
                "WHERE receipt_digest=? AND length(receipt)<=4096 AND length(artifact)<=?",
                (digest, self.max_artifact_bytes),
            ).fetchone()
        if row is None:
            return None
        try:
            receipt = HostWorkerReceipt(**json.loads(row[4]))
            artifact = row[5]
            if (type(artifact) is not bytes or receipt.digest != digest
                    or receipt.artifact_sha256 != sha256(artifact).hexdigest()
                    or (receipt.run_id, receipt.lease_token, receipt.worker_id, receipt.task_id)
                    != row[:4]):
                return None
            return receipt, artifact
        except (TypeError, ValueError, DurableSwarmError):
            return None

    def lookup(self, run_id: str, lease_token: str) -> LocalAttemptRecord | None:
        from contextlib import closing
        _wait_identifier(run_id)
        if (type(lease_token) is not str or len(lease_token) != 32
                or any(char not in "0123456789abcdef" for char in lease_token)):
            raise DurableSwarmError("invalid local attempt lookup token")
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT tenant,task_id,worker_id,payload,receipt_digest FROM attempts "
                "WHERE run_id=? AND lease_token=? AND length(payload)<=65536",
                (run_id, lease_token),
            ).fetchone()
        if row is None:
            return None
        attempt = HostDispatchAttempt(run_id, row[0], row[1], row[2], lease_token, row[3])
        _check_local_attempt(attempt)
        if row[4] is not None:
            _wait_digest(row[4])
        return LocalAttemptRecord(attempt, row[4])

    def usage(self) -> dict[str, int]:
        from contextlib import closing
        with closing(self._connect()) as conn:
            count, charge, completed = conn.execute(
                "SELECT count(*),coalesce(sum(charge),0),count(receipt_digest) FROM attempts"
            ).fetchone()
        return {"attempts": count, "reserved_bytes": charge,
                "completed": completed, "uncertain": count - completed}


_LOCAL_OPERATIONS = frozenset({"sha256_text", "integer_sum", "json_sha256"})


def _local_reference(payload: dict[str, object]) -> object:
    """Independent owner-side semantic validation for bounded pure operations."""
    from hashlib import sha256
    if type(payload) is not dict or set(payload) != {"operation", "input"}:
        raise DurableSwarmError("invalid local operation request")
    operation, value = payload["operation"], payload["input"]
    if type(operation) is not str or operation not in _LOCAL_OPERATIONS:
        raise DurableSwarmError("local operation not approved")
    if operation == "sha256_text":
        if type(value) is not str:
            raise DurableSwarmError("text digest requires text")
        return sha256(value.encode("utf-8")).hexdigest()
    if operation == "integer_sum":
        if (type(value) is not list or len(value) > 8192
                or any(type(item) is not int or abs(item) > 2**53 for item in value)):
            raise DurableSwarmError("invalid bounded integer input")
        result = 0
        for item in value:
            result += item
        return result
    if type(value) not in (dict, list):
        raise DurableSwarmError("JSON digest requires object or array")
    return sha256(_wait_bytes(value)).hexdigest()


# The interpreter program is constant, never constructed from a task. There
# is no shell, arbitrary command, dynamic import or untrusted executable.
_LOCAL_WORKER_PROGRAM = """
import hashlib, json, sys
request = json.loads(sys.stdin.buffer.read(65537))
operation, value = request["operation"], request["input"]
if operation == "sha256_text":
    result = hashlib.sha256(value.encode("utf-8")).hexdigest()
elif operation == "integer_sum":
    result = sum(value)
elif operation == "json_sha256":
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    result = hashlib.sha256(raw.encode("ascii")).hexdigest()
else:
    raise ValueError("operation unavailable")
sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False))
"""


class LocalWorkerEvidenceValidator:
    """Recompute pure job semantics from persisted admitted input, not claims."""

    def __init__(self, custody: SQLiteWorkerCustody) -> None:
        self.custody = custody

    def __call__(self, receipt: HostWorkerReceipt, artifact: bytes) -> bool:
        import json
        from hashlib import sha256
        if receipt.action != "success":
            return False
        record = self.custody.lookup(receipt.run_id, receipt.lease_token)
        if record is None or record.receipt_sha256 != receipt.digest:
            return False
        attempt = record.attempt
        if (attempt.task_id, attempt.worker_id) != (receipt.task_id, receipt.worker_id):
            return False
        expected = {"version": 1,
                    "payload_sha256": sha256(attempt.payload_json).hexdigest(),
                    "result": _local_reference(attempt.payload())}
        return artifact == _wait_bytes(expected)


class LocalSubprocessTransport:
    """Real bounded process execution for explicitly granted local pure jobs.

    Uses a host-owned interpreter and a fixed worker program. This is not a
    sandbox for arbitrary code, a model runner, or an external tool executor.
    Uncertain transport outcomes are held by HostDispatchService.
    """

    def __init__(self, custody: SQLiteWorkerCustody, *,
                 grants: dict[tuple[str, str], frozenset[str]],
                 worker_signers: dict[str, tuple[str, bytes]],
                 timeout_seconds: float = 5.0) -> None:
        import math
        if (type(grants) is not dict or len(grants) > 4096
                or type(worker_signers) is not dict or len(worker_signers) > 4096
                or type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 60):
            raise DurableSwarmError("invalid local transport configuration")
        self.custody = custody
        self._grants = {}
        self._signers = {}
        for worker, signer in worker_signers.items():
            if type(signer) is not tuple or len(signer) != 2:
                raise DurableSwarmError("invalid local worker signer")
            issuer, key = signer
            _validate_wait_key(key)
            self._signers[_wait_identifier(worker)] = (_wait_identifier(issuer), key)
        for scope, operations in grants.items():
            if type(scope) is not tuple or len(scope) != 2:
                raise DurableSwarmError("invalid local transport scope")
            tenant, worker = scope
            if (worker not in self._signers or type(operations) is not frozenset
                    or not operations or not operations.issubset(_LOCAL_OPERATIONS)):
                raise DurableSwarmError("invalid local operation grant")
            self._grants[(_wait_identifier(tenant), _wait_identifier(worker))] = operations
        self.timeout_seconds = timeout_seconds

    def __call__(self, attempt: HostDispatchAttempt) -> HostTransportReply:
        import json
        import os
        import subprocess
        import sys
        from hashlib import sha256
        _check_local_attempt(attempt)
        payload = attempt.payload()
        expected = _local_reference(payload)
        if payload["operation"] not in self._grants.get((attempt.tenant, attempt.worker_id), ()):
            raise DurableSwarmError("local operation not granted for tenant and worker")
        if not self.custody.begin(attempt):
            previous = self.custody.lookup(attempt.run_id, attempt.lease_token)
            if previous is None or previous.receipt_sha256 is None:
                raise DurableSwarmError("existing local attempt has uncertain effects")
            resolved = self.custody.resolve(previous.receipt_sha256)
            if resolved is None:
                raise DurableSwarmError("existing local result custody is invalid")
            return HostTransportReply(resolved[0].action, previous.receipt_sha256)
        env = {}
        if os.name == "nt" and "SystemRoot" in os.environ:
            env["SystemRoot"] = os.environ["SystemRoot"]
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _LOCAL_WORKER_PROGRAM],
            input=attempt.payload_json, capture_output=True, timeout=self.timeout_seconds,
            cwd=self.custody.directory, env=env, shell=False, close_fds=True, check=False,
        )
        # The fixed worker program produces only a bounded scalar. A modified
        # interpreter is outside the trusted host boundary.
        if result.returncode != 0 or len(result.stdout) > 256 or result.stderr:
            raise DurableSwarmError("local worker process failed")
        value = json.loads(result.stdout)
        if type(value) is not type(expected) or value != expected:
            raise DurableSwarmError("local worker result failed independent verification")
        artifact = _wait_bytes({"version": 1,
                                "payload_sha256": sha256(attempt.payload_json).hexdigest(),
                                "result": value})
        issuer, key = self._signers[attempt.worker_id]
        receipt = HostWorkerReceipt.issue(
            run_id=attempt.run_id, issuer=issuer, worker_id=attempt.worker_id,
            task_id=attempt.task_id, lease_token=attempt.lease_token, action="success",
            artifact_sha256=sha256(artifact).hexdigest(), issuer_key=key,
        )
        digest = self.custody.finish(attempt, receipt, artifact)
        return HostTransportReply("success", digest)
