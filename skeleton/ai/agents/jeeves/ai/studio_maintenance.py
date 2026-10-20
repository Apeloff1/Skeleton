"""Host-owned, cooperative maintenance within the existing idle effect ledger.

This is a controller called by the engine lifespan, never a background service.
Only explicitly registered, repeat-safe local derived-state handlers may run.
Every chunk still traverses the idle scheduler, exact host authorization and
durable effect receipts. Neither this controller nor its queue executes model
providers, fetches sources, trains model weights or promotes a candidate.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
import sys
from pathlib import Path
from socket import gethostname
from threading import Lock, RLock
from time import monotonic_ns, time_ns
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .idle_learning_runtime import (
    HostIdleWorkReceipt, IdleExecutionState, IdleRuntimeError, IdleWorkBudget,
    IdleWorkCheckpoint, IdleWorkPreempted, JeevesIdleWorkExecutor,
)
from .idle_learning_scheduler import (
    HostIdleTelemetry, IdleLearningPolicy, IdleWorkAssignment, IdleWorkCandidate,
    IdleWorkKind, JeevesIdleLearningScheduler,
)


LOCAL_MAINTENANCE_KINDS = frozenset({
    IdleWorkKind.CACHE_CLEANUP,
    IdleWorkKind.CHECKPOINT_COMPACTION,
    IdleWorkKind.REPLAY_DEDUP,
    IdleWorkKind.LEARNER_SNAPSHOT,
    IdleWorkKind.ELIGIBLE_AUGMENTATION,
})
_MAX_PAYLOAD_BYTES = 16_384
_MAX_OUTPUT_BYTES = 32_768
_MAX_RETAINED_EVENTS = 4096
_MAX_CHUNK_BYTES = 65_536
_TASK_COLUMNS = (
    "task_id,scope_id,kind,source_digest,payload_digest,payload_json,priority,"
    "state,attempts,failures,next_run_ns,created_at_ns,updated_at_ns,"
    "lease_until_ns,last_error,last_intent,output_digest,owner_id,host_id,"
    "host_fence,scope_fence,heartbeat_ns,drained_at_ns,continuation_index,continuation_id,handler_version"
)
_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_task (
    task_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    priority INTEGER NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    next_run_ns INTEGER NOT NULL,
    created_at_ns INTEGER NOT NULL,
    updated_at_ns INTEGER NOT NULL,
    lease_until_ns INTEGER NOT NULL,
    last_error TEXT,
    last_intent TEXT,
    output_digest TEXT
);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_ready
    ON jeeves_idle_maintenance_task(state,next_run_ns,priority);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_scope_queue
    ON jeeves_idle_maintenance_task(scope_id,state,next_run_ns);
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_circuit (
    scope_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    failures INTEGER NOT NULL,
    open_until_ns INTEGER NOT NULL,
    last_error TEXT,
    PRIMARY KEY(scope_id,kind)
);
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_event (
    sequence INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    at_ns INTEGER NOT NULL,
    detail_digest TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_owner (
    owner_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL,
    boot_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    process_start TEXT NOT NULL,
    process_namespace TEXT NOT NULL,
    state TEXT NOT NULL,
    heartbeat_ns INTEGER NOT NULL,
    foreground_requests INTEGER NOT NULL,
    physical_tasks INTEGER NOT NULL,
    last_foreground_ns INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_host_owner
    ON jeeves_idle_maintenance_owner(host_id,state);
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_lease (
    resource_id TEXT PRIMARY KEY,
    scope_id TEXT,
    owner_id TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    state TEXT NOT NULL,
    heartbeat_ns INTEGER NOT NULL,
    lease_until_ns INTEGER NOT NULL,
    drained_at_ns INTEGER,
    task_id TEXT
);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_scope_lease
    ON jeeves_idle_maintenance_lease(scope_id,state);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_task_lease
    ON jeeves_idle_maintenance_lease(task_id,state);
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_clock (
    host_id TEXT PRIMARY KEY,
    boot_id TEXT NOT NULL,
    wall_ns INTEGER NOT NULL,
    monotonic_ns INTEGER NOT NULL,
    logical_ns INTEGER NOT NULL,
    jump_count INTEGER NOT NULL,
    last_jump_reason TEXT
);
CREATE TABLE IF NOT EXISTS jeeves_idle_maintenance_chunk (
    continuation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    handler_version TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    task_json TEXT NOT NULL,
    result_json TEXT,
    result_digest TEXT,
    recorded_at_ns INTEGER NOT NULL,
    producer_owner_id TEXT NOT NULL,
    producer_attempt INTEGER NOT NULL,
    producer_fence INTEGER NOT NULL,
    verified_intent_digest TEXT,
    verified_receipt_json TEXT,
    verified_receipt_digest TEXT,
    verified_at_ns INTEGER,
    ack_state TEXT NOT NULL,
    ack_failures INTEGER NOT NULL,
    next_ack_ns INTEGER NOT NULL,
    last_ack_error TEXT
);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_chunk_ack
    ON jeeves_idle_maintenance_chunk(ack_state,next_ack_ns);
CREATE INDEX IF NOT EXISTS jeeves_idle_maintenance_chunk_scope
    ON jeeves_idle_maintenance_chunk(scope_id,ack_state);
"""


def _host_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = stream.read(8192).strip()
        return value or None
    except (OSError, UnicodeError):
        return None


def _process_start(process_id: int) -> str | None:
    raw = _host_text(f"/proc/{process_id}/stat")
    if raw is None or ")" not in raw:
        return None
    fields = raw.rsplit(")", 1)[1].split()
    return fields[19] if len(fields) > 19 and fields[19].isdigit() else None


def _local_identity(*, owner_id: str | None = None, host_id: str | None = None) -> dict[str, Any]:
    boot = _host_text("/proc/sys/kernel/random/boot_id")
    machine = _host_text("/etc/machine-id") or gethostname()
    try:
        namespace = os.readlink("/proc/self/ns/pid")
    except OSError:
        namespace = "unavailable" if sys.platform.startswith("linux") else "native-process-namespace"
    host = host_id or _digest({"hostname": gethostname(), "machine": machine,
                               "pid_namespace": namespace})
    return {
        "owner_id": _identifier(owner_id or "maintenance-" + uuid4().hex, "owner"),
        "host_id": _identifier(host, "host"),
        "boot_id": _digest(boot) if boot is not None else "unavailable",
        "process_id": os.getpid(),
        "process_start": _process_start(os.getpid()) or "unavailable",
        "process_namespace": _digest(namespace) if namespace != "unavailable" else "unavailable",
    }


def _canonical(value: Any, *, maximum_bytes: int = _MAX_PAYLOAD_BYTES) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise IdleRuntimeError("maintenance metadata must be finite JSON") from exc
    if len(raw.encode("utf-8")) > maximum_bytes:
        raise IdleRuntimeError("maintenance metadata exceeds its chunk budget")
    return raw


def _digest(value: Any, *, maximum_bytes: int = _MAX_OUTPUT_BYTES) -> str:
    return sha256(_canonical(value, maximum_bytes=maximum_bytes).encode("utf-8")).hexdigest()


def _identifier(value: Any, label: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 192
            or value.strip() != value or any(ord(char) < 33 for char in value)):
        raise IdleRuntimeError(f"maintenance {label} must be a bounded identifier")
    return value


def _sha(value: Any) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise IdleRuntimeError("maintenance source identity must be SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class StudioMaintenancePolicy:
    enabled: bool = False
    augmentation_enabled: bool = False
    maximum_tasks_per_tick: int = 1
    maximum_queue: int = 512
    maximum_retained_tasks: int = 256
    maximum_chunk_wall_ms: int = 1000
    maximum_chunk_cpu_ms: int = 500
    maximum_chunk_polls: int = 512
    maximum_memory_drop_ppm: int = 100_000
    maximum_consecutive_failures: int = 5
    initial_backoff_ms: int = 1000
    maximum_backoff_ms: int = 300_000
    preemption_backoff_ms: int = 1000
    circuit_failure_threshold: int = 3
    circuit_cooldown_ms: int = 60_000
    interrupted_lease_grace_ms: int = 10_000
    maximum_scope_queue: int = 128
    priority_aging_ms: int = 30_000
    clock_jump_tolerance_ms: int = 5000
    maximum_owner_heartbeat_ms: int = 15_000
    maximum_chunk_results: int = 1024
    maximum_ack_retries_per_tick: int = 4

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or type(self.augmentation_enabled) is not bool:
            raise IdleRuntimeError("maintenance policy enablement must be explicit boolean")
        bounds = {
            "maximum_tasks_per_tick": (1, 8),
            "maximum_queue": (1, 8192),
            "maximum_retained_tasks": (1, 8192),
            "maximum_chunk_wall_ms": (1, 5000),
            "maximum_chunk_cpu_ms": (1, 5000),
            "maximum_chunk_polls": (4, 65_536),
            "maximum_memory_drop_ppm": (0, 1_000_000),
            "maximum_consecutive_failures": (1, 32),
            "initial_backoff_ms": (1, 300_000),
            "maximum_backoff_ms": (1, 86_400_000),
            "preemption_backoff_ms": (1, 300_000),
            "circuit_failure_threshold": (1, 32),
            "circuit_cooldown_ms": (1, 86_400_000),
            "interrupted_lease_grace_ms": (1000, 300_000),
            "maximum_scope_queue": (1, 8192),
            "priority_aging_ms": (1000, 86_400_000),
            "clock_jump_tolerance_ms": (100, 60_000),
            "maximum_owner_heartbeat_ms": (1000, 300_000),
            "maximum_chunk_results": (1, 16_384),
            "maximum_ack_retries_per_tick": (1, 16),
        }
        for key, (minimum, maximum) in bounds.items():
            value = getattr(self, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise IdleRuntimeError(f"maintenance {key} must be {minimum}..{maximum}")
        if self.initial_backoff_ms > self.maximum_backoff_ms:
            raise IdleRuntimeError("maintenance backoff bounds are inconsistent")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "StudioMaintenancePolicy":
        if not isinstance(values, Mapping):
            raise IdleRuntimeError("maintenance policy must be an object")
        if set(values) - set(cls.__dataclass_fields__):
            raise IdleRuntimeError("unknown maintenance policy field")
        return cls(**dict(values))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MaintenanceTask:
    task_id: str
    scope_id: str
    kind: IdleWorkKind
    source_digest: str
    payload: Mapping[str, Any]
    attempt: int
    priority: int
    created_at_ns: int
    owner_id: str = ""
    host_id: str = ""
    fencing_token: int = 0
    host_fencing_token: int = 0
    continuation_index: int = 0
    continuation_id: str = ""
    handler_version: str = "1"


@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    """A bounded chunk result; incomplete work supplies its next local cursor."""

    output: Mapping[str, Any]
    complete: bool = True
    continuation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.output, Mapping) or type(self.complete) is not bool:
            raise IdleRuntimeError("maintenance result must be a typed finite mapping")
        _canonical(dict(self.output), maximum_bytes=_MAX_OUTPUT_BYTES)
        if self.continuation is not None:
            if not isinstance(self.continuation, Mapping):
                raise IdleRuntimeError("maintenance continuation must be a finite object")
            _canonical(dict(self.continuation))
        if self.complete and self.continuation is not None:
            raise IdleRuntimeError("completed maintenance may not install a continuation")


@dataclass(frozen=True, slots=True)
class MaintenanceHandler:
    """Host declaration that a local handler safely tolerates repeated chunks.

    Use the stable task_id for local candidate/snapshot idempotency. A handler
    may compact derived replay buffers, never authoritative terminal receipts.
    Handlers execute synchronously in the owner process and drain all physical
    work before returning; detached threads or subprocess work are not allowed.
    """

    callback: Callable[[MaintenanceTask, IdleWorkCheckpoint], Mapping[str, Any] | MaintenanceResult]
    retry_safe: bool
    version: str = "1"

    def __post_init__(self) -> None:
        if not callable(self.callback) or self.retry_safe is not True:
            raise IdleRuntimeError("maintenance requires an explicit retry-safe host callback")
        _identifier(self.version, "handler version")


@dataclass(slots=True)
class _AttemptContext:
    task: MaintenanceTask
    handler: MaintenanceHandler
    output: MaintenanceResult | None = None
    receipt: HostIdleWorkReceipt | None = None
    controller: StudioMaintenanceController | None = None


class StudioMaintenanceController:
    """One lifespan-owned local worker with durable, priority-ordered tasks.

    The injected executor is the existing idle-effect authority. Its connection
    may point at the existing execution repository file; no parallel database is
    required. The controller starts no thread or timer and tick() never waits for
    another tick. Foreground accounting is independent of the persistence lock.
    """

    def __init__(
        self, *, executor: JeevesIdleWorkExecutor,
        callbacks: Mapping[IdleWorkKind, MaintenanceHandler],
        policy: StudioMaintenancePolicy | None = None,
        owns_executor: bool = False,
        owner_id: str | None = None,
        host_id: str | None = None,
        host_confirm_drained: Callable[[Mapping[str, Any]], bool | None] | None = None,
        after_verified_chunk: Callable[[MaintenanceTask, MaintenanceResult, HostIdleWorkReceipt], Any] | None = None,
    ) -> None:
        if not isinstance(executor, JeevesIdleWorkExecutor):
            raise IdleRuntimeError("maintenance requires the existing idle executor")
        self._handlers = _validate_handlers(callbacks)
        self._executor = executor
        self._policy = policy or StudioMaintenancePolicy()
        if not isinstance(self._policy, StudioMaintenancePolicy):
            raise IdleRuntimeError("maintenance requires typed policy")
        self._owns_executor = owns_executor
        if host_confirm_drained is not None and not callable(host_confirm_drained):
            raise IdleRuntimeError("maintenance drain verifier must be host-owned")
        self._identity = _local_identity(owner_id=owner_id, host_id=host_id)
        self._host_confirm_drained = host_confirm_drained
        if after_verified_chunk is not None and not callable(after_verified_chunk):
            raise IdleRuntimeError("verified maintenance acknowledgement must be host-owned")
        self._after_verified_chunk = after_verified_chunk
        self._state_lock = RLock()
        self._tick_lock = Lock()
        self._foreground_requests = 0
        self._foreground_generation = 0
        self._last_foreground_mono_ns = monotonic_ns()
        self._closed = False
        self._closing = False
        self._active_tasks = 0
        self._last_run_ns: int | None = None
        self._last_reason = "disabled" if not self._policy.enabled else "idle"
        self._coordination_fault: str | None = None
        self._last_logical_ns = 0
        with self._executor._lock:
            self._executor._db.executescript(_QUEUE_SCHEMA)
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                columns = {row[1] for row in db.execute("PRAGMA table_info(jeeves_idle_maintenance_task)")}
                additions = {
                    "owner_id": "TEXT", "host_id": "TEXT",
                    "host_fence": "INTEGER NOT NULL DEFAULT 0",
                    "scope_fence": "INTEGER NOT NULL DEFAULT 0",
                    "heartbeat_ns": "INTEGER NOT NULL DEFAULT 0",
                    "drained_at_ns": "INTEGER",
                    "continuation_index": "INTEGER NOT NULL DEFAULT 0",
                    "continuation_id": "TEXT",
                    "handler_version": "TEXT NOT NULL DEFAULT ''",
                    "recovery_checked_ns": "INTEGER NOT NULL DEFAULT 0",
                }
                for name, declaration in additions.items():
                    if name not in columns:
                        db.execute(f"ALTER TABLE jeeves_idle_maintenance_task ADD COLUMN {name} {declaration}")
                owner_columns = {row[1] for row in db.execute("PRAGMA table_info(jeeves_idle_maintenance_owner)")}
                if "process_namespace" not in owner_columns:
                    db.execute("ALTER TABLE jeeves_idle_maintenance_owner ADD COLUMN "
                               "process_namespace TEXT NOT NULL DEFAULT 'unavailable'")
                now = self._logical_now_locked(time_ns(), self._policy)
                if db.execute("SELECT 1 FROM jeeves_idle_maintenance_owner WHERE owner_id=?",
                              (self._identity["owner_id"],)).fetchone() is not None:
                    raise IdleRuntimeError("maintenance owner identity must be unique per controller lifespan")
                db.execute(
                    "INSERT INTO jeeves_idle_maintenance_owner "
                    "(owner_id,host_id,boot_id,process_id,process_start,process_namespace,"
                    "state,heartbeat_ns,foreground_requests,physical_tasks,last_foreground_ns) "
                    "VALUES (?,?,?,?,?,?,'live',?,0,0,?)",
                    (self._identity["owner_id"], self._identity["host_id"], self._identity["boot_id"],
                     self._identity["process_id"], self._identity["process_start"],
                     self._identity["process_namespace"], now, now),
                )
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _logical_now_locked(self, wall_ns: int, policy: StudioMaintenancePolicy) -> int:
        """Monotonic host clock for persisted leases and backoff, across workers.

        Epoch telemetry remains the scheduler's freshness authority. Durable
        lease arithmetic follows the shared host monotonic clock, so an NTP or
        manual wall-clock change cannot prematurely transfer live ownership.
        """
        db = self._executor._db
        mono = monotonic_ns()
        row = db.execute(
            "SELECT boot_id,wall_ns,monotonic_ns,logical_ns,jump_count,last_jump_reason "
            "FROM jeeves_idle_maintenance_clock WHERE host_id=?", (self._identity["host_id"],),
        ).fetchone()
        count, reason = (0, None) if row is None else (row[4], row[5])
        if row is None:
            logical = wall_ns
        elif row[0] != self._identity["boot_id"] or mono < row[2]:
            logical = max(row[3], wall_ns)
            count += 1
            reason = "host_clock_restarted"
        else:
            elapsed = mono - row[2]
            logical = row[3] + elapsed
            divergence = wall_ns - row[1] - elapsed
            if abs(divergence) > policy.clock_jump_tolerance_ms * 1_000_000:
                count += 1
                reason = "wall_clock_forward" if divergence > 0 else "wall_clock_backward"
        db.execute(
            "INSERT INTO jeeves_idle_maintenance_clock VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(host_id) DO UPDATE SET boot_id=excluded.boot_id,wall_ns=excluded.wall_ns,"
            "monotonic_ns=excluded.monotonic_ns,logical_ns=excluded.logical_ns,"
            "jump_count=excluded.jump_count,last_jump_reason=excluded.last_jump_reason",
            (self._identity["host_id"], self._identity["boot_id"], wall_ns, mono, logical, count, reason),
        )
        self._last_logical_ns = logical
        return logical

    def _logical_now(self, wall_ns: int | None = None) -> int:
        policy = self.policy
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now = self._logical_now_locked(time_ns() if wall_ns is None else wall_ns, policy)
                db.execute("COMMIT")
                return now
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _owner_drained(self, owner_id: str | None) -> bool:
        """Positive drain proof only; lease timeout and missing rows prove none."""
        row = None if owner_id is None else self._executor._db.execute(
            "SELECT owner_id,host_id,boot_id,process_id,process_start,process_namespace,state,physical_tasks "
            "FROM jeeves_idle_maintenance_owner WHERE owner_id=?", (owner_id,),
        ).fetchone()
        keys = ("owner_id", "host_id", "boot_id", "process_id", "process_start", "process_namespace", "state", "physical_tasks")
        info = {"owner_id": owner_id, "state": "unproven"} if row is None else dict(zip(keys, row))
        if row is not None:
            if owner_id == self._identity["owner_id"] and self._active_tasks == 0:
                # The controller's tick lock is held by recovery. This exact
                # lifespan knows a prior failed finalization physically drained.
                return True
            if info["state"] == "drained" and info["physical_tasks"] == 0:
                return True
            if info["host_id"] == self._identity["host_id"]:
                if (info["boot_id"] != "unavailable" and self._identity["boot_id"] != "unavailable"
                        and info["boot_id"] != self._identity["boot_id"]):
                    return True
                if (info["process_namespace"] == "unavailable"
                        or info["process_namespace"] != self._identity["process_namespace"]):
                    # A host-name override cannot authorize probing another
                    # container's numeric PID in this process namespace.
                    if self._host_confirm_drained is None:
                        return False
                    try:
                        return self._host_confirm_drained(MappingProxyType(info)) is True
                    except Exception:
                        return False
                start = _process_start(info["process_id"])
                if start is not None and info["process_start"] != "unavailable":
                    if start != info["process_start"]:
                        return True
                else:
                    try:
                        os.kill(info["process_id"], 0)
                    except ProcessLookupError:
                        return True
                    except (OSError, OverflowError, ValueError):
                        pass  # permission/namespace uncertainty is not proof
        if self._host_confirm_drained is None:
            return False
        try:
            return self._host_confirm_drained(MappingProxyType(info)) is True
        except Exception:
            return False

    def heartbeat(self) -> bool:
        """Lifespan hook; checkpoints additionally heartbeat the active fences."""
        with self._state_lock:
            if self._closed:
                return False
            foreground, physical = self._foreground_requests, self._active_tasks
            activity_mono = self._last_foreground_mono_ns
            state = "draining" if self._closing else "live"
            # Serialize the local counters through the commit. A concurrent
            # foreground edge must never be overwritten by an older snapshot.
            with self._executor._lock:
                db = self._executor._db
                try:
                    db.execute("BEGIN IMMEDIATE")
                    now = self._logical_now_locked(time_ns(), self._policy)
                    activity = max(0, now - max(0, monotonic_ns() - activity_mono))
                    changed = db.execute(
                        "UPDATE jeeves_idle_maintenance_owner SET state=?,heartbeat_ns=?,"
                        "foreground_requests=?,physical_tasks=?,last_foreground_ns="
                        "MAX(last_foreground_ns,?) WHERE owner_id=?",
                        (state, now, foreground, physical, activity, self._identity["owner_id"]),
                    ).rowcount
                    if changed != 1:
                        raise IdleRuntimeError("maintenance owner presence is unavailable")
                    db.execute("COMMIT")
                    self._coordination_fault = None
                    return True
                except BaseException as exc:
                    self._coordination_fault = type(exc).__name__
                    self._last_reason = "coordination_unavailable"
                    if db.in_transaction:
                        db.execute("ROLLBACK")
                    raise

    @property
    def policy(self) -> StudioMaintenancePolicy:
        with self._state_lock:
            return self._policy

    def configure(self, policy: StudioMaintenancePolicy) -> dict[str, Any]:
        if not isinstance(policy, StudioMaintenancePolicy):
            raise IdleRuntimeError("maintenance requires typed policy")
        with self._state_lock:
            if self._closed or self._closing:
                raise IdleRuntimeError("maintenance controller is closing")
            self._policy = policy
            # A policy change invalidates admission made against the old one.
            self._foreground_generation += 1
            self._last_foreground_mono_ns = monotonic_ns()
            self._last_reason = "idle" if policy.enabled else "disabled"
        return self.snapshot()

    def foreground_started(self) -> None:
        """Call before queueing foreground work, including resumed executions."""
        with self._state_lock:
            self._foreground_requests += 1
            self._foreground_generation += 1
            self._last_foreground_mono_ns = monotonic_ns()
            self._last_reason = "foreground_preemption"
        self.heartbeat()

    def foreground_finished(self) -> None:
        with self._state_lock:
            self._foreground_requests = max(0, self._foreground_requests - 1)
            self._last_foreground_mono_ns = monotonic_ns()
        self.heartbeat()

    def synchronize_foreground(self, count: int) -> None:
        """Trusted lifespan initialization/recovery; model proposals cannot call it."""
        if type(count) is not int or not 0 <= count <= 10_000:
            raise IdleRuntimeError("host foreground count must be 0..10000")
        with self._state_lock:
            self._foreground_requests = count
            self._foreground_generation += 1
            self._last_foreground_mono_ns = monotonic_ns()
        self.heartbeat()

    def _preempted(self, generation: int) -> bool:
        with self._state_lock:
            return (self._closing or self._closed or not self._policy.enabled
                    or self._coordination_fault is not None
                    or self._foreground_requests > 0
                    or generation != self._foreground_generation)

    def _now(self) -> tuple[HostIdleTelemetry, int]:
        observed = self._executor._telemetry_probe()
        if (not isinstance(observed, tuple) or len(observed) != 2
                or not isinstance(observed[0], HostIdleTelemetry)
                or type(observed[1]) is not int or observed[1] < 0):
            raise IdleRuntimeError("maintenance requires fresh trusted host telemetry")
        return observed

    @staticmethod
    def _work_id(task_id: str, attempt: int) -> str:
        return f"maintenance-{task_id}-{attempt}"

    def _host_idle_locked(self, now_ns: int) -> bool:
        db = self._executor._db
        owners = db.execute(
            "SELECT owner_id,foreground_requests,last_foreground_ns,heartbeat_ns,state FROM "
            "jeeves_idle_maintenance_owner WHERE host_id=? AND state!='drained' LIMIT 1025",
            (self._identity["host_id"],),
        ).fetchall()
        if len(owners) > 1024:
            return False
        for owner, foreground, last_foreground, heartbeat, state in owners:
            if owner != self._identity["owner_id"] and self._owner_drained(owner):
                db.execute(
                    "UPDATE jeeves_idle_maintenance_owner SET state='drained',"
                    "foreground_requests=0,physical_tasks=0 WHERE owner_id=?", (owner,),
                )
                continue
            if (state != "live" or foreground
                    or now_ns - heartbeat > self._policy.maximum_owner_heartbeat_ms * 1_000_000
                    or now_ns - last_foreground < self._executor.policy.minimum_idle_ns):
                return False
        return True

    def _acquire_resource_locked(self, resource_id: str, scope_id: str | None,
                                 task_id: str, now_ns: int, lease_ns: int) -> int | None:
        db = self._executor._db
        row = db.execute(
            "SELECT owner_id,fencing_token,state,lease_until_ns,task_id FROM "
            "jeeves_idle_maintenance_lease WHERE resource_id=?", (resource_id,),
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO jeeves_idle_maintenance_lease VALUES (?,?,?,1,'held',?,?,NULL,?)",
                (resource_id, scope_id, self._identity["owner_id"], now_ns, now_ns + lease_ns, task_id),
            )
            return 1
        owner, token, state, expires, prior_task = row
        if state != "released" and (expires > now_ns or not self._owner_drained(owner)):
            return None
        if state != "released" and prior_task is not None and db.execute(
            "SELECT 1 FROM jeeves_idle_maintenance_task WHERE task_id=? AND state='running'",
            (prior_task,),
        ).fetchone() is not None:
            # Recover both old fences and its task in one transaction first.
            # Stealing just the host fence can otherwise orphan the old scope.
            return None
        changed = db.execute(
            "UPDATE jeeves_idle_maintenance_lease SET owner_id=?,fencing_token=?,state='held',"
            "heartbeat_ns=?,lease_until_ns=?,drained_at_ns=NULL,task_id=? "
            "WHERE resource_id=? AND owner_id=? AND fencing_token=? AND state=?",
            (self._identity["owner_id"], token + 1, now_ns, now_ns + lease_ns,
             task_id, resource_id, owner, token, state),
        ).rowcount
        return token + 1 if changed == 1 else None

    def _release_resources_locked(self, task: MaintenanceTask, now_ns: int) -> None:
        for resource, token in (("host:" + task.host_id, task.host_fencing_token),
                                ("scope:" + task.scope_id, task.fencing_token)):
            updated = self._executor._db.execute(
                "UPDATE jeeves_idle_maintenance_lease SET state='released',lease_until_ns=0,"
                "drained_at_ns=?,heartbeat_ns=? WHERE resource_id=? AND owner_id=? "
                "AND fencing_token=? AND state='held' AND task_id=?",
                (now_ns, now_ns, resource, task.owner_id, token, task.task_id),
            )
            if updated.rowcount != 1:
                raise IdleRuntimeError("maintenance release lost its ownership fence")

    def _release_drained_resources_locked(self, task: MaintenanceTask, now_ns: int) -> None:
        """Recovery only, after positive physical drain of the prior owner.

        A newer fence may already exist after an older-version takeover. Never
        mutate that worker's lease; retire only the exact old custody still held.
        """
        for resource, token in (("host:" + task.host_id, task.host_fencing_token),
                                ("scope:" + task.scope_id, task.fencing_token)):
            self._executor._db.execute(
                "UPDATE jeeves_idle_maintenance_lease SET state='released',lease_until_ns=0,"
                "drained_at_ns=?,heartbeat_ns=? WHERE resource_id=? AND owner_id=? "
                "AND fencing_token=? AND state='held' AND task_id=?",
                (now_ns, now_ns, resource, task.owner_id, token, task.task_id),
            )

    def _heartbeat_task(self, task: MaintenanceTask, policy: StudioMaintenancePolicy) -> bool:
        """Renew only the exact physical worker's scope and host fences."""
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now = self._logical_now_locked(time_ns(), policy)
                if not self._host_idle_locked(now):
                    db.execute("ROLLBACK")
                    return False
                until = now + (policy.maximum_chunk_wall_ms
                               + policy.interrupted_lease_grace_ms) * 1_000_000
                for resource, token in (("host:" + task.host_id, task.host_fencing_token),
                                        ("scope:" + task.scope_id, task.fencing_token)):
                    changed = db.execute(
                        "UPDATE jeeves_idle_maintenance_lease SET heartbeat_ns=?,lease_until_ns=? "
                        "WHERE resource_id=? AND owner_id=? AND fencing_token=? "
                        "AND state='held' AND task_id=?",
                        (now, until, resource, task.owner_id, token, task.task_id),
                    ).rowcount
                    if changed != 1:
                        db.execute("ROLLBACK")
                        return False
                changed = db.execute(
                    "UPDATE jeeves_idle_maintenance_task SET heartbeat_ns=?,lease_until_ns=? "
                    "WHERE task_id=? AND owner_id=? AND attempts=? AND scope_fence=? "
                    "AND host_fence=? AND state='running'",
                    (now, until, task.task_id, task.owner_id, task.attempt,
                     task.fencing_token, task.host_fencing_token),
                ).rowcount
                if changed != 1:
                    db.execute("ROLLBACK")
                    return False
                db.execute(
                    "UPDATE jeeves_idle_maintenance_owner SET heartbeat_ns=?,physical_tasks=1 "
                    "WHERE owner_id=? AND state='live'", (now, task.owner_id),
                )
                db.execute("COMMIT")
                return True
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _event(self, task_id: str, operation: str, now_ns: int,
               detail: Mapping[str, Any]) -> None:
        """Bounded operational projection; effect receipts are never compacted."""
        raw = _canonical(dict(detail))
        self._executor._db.execute(
            "INSERT INTO jeeves_idle_maintenance_event "
            "(task_id,operation,at_ns,detail_digest,detail_json) VALUES (?,?,?,?,?)",
            (task_id, operation, now_ns, sha256(raw.encode("utf-8")).hexdigest(), raw),
        )
        self._executor._db.execute(
            "DELETE FROM jeeves_idle_maintenance_event WHERE sequence <= "
            "(SELECT MAX(sequence)-? FROM jeeves_idle_maintenance_event)",
            (_MAX_RETAINED_EVENTS,),
        )

    @staticmethod
    def _task_json(task: MaintenanceTask) -> str:
        return _canonical({
            "task_id": task.task_id, "scope_id": task.scope_id, "kind": task.kind.value,
            "source_digest": task.source_digest, "payload_json": _canonical(dict(task.payload)),
            "attempts": task.attempt, "priority": task.priority, "created_at_ns": task.created_at_ns,
            "owner_id": task.owner_id, "host_id": task.host_id, "scope_fence": task.fencing_token,
            "host_fence": task.host_fencing_token, "continuation_index": task.continuation_index,
            "continuation_id": task.continuation_id, "handler_version": task.handler_version,
        }, maximum_bytes=_MAX_OUTPUT_BYTES)

    @staticmethod
    def _result_json(result: MaintenanceResult) -> str:
        return _canonical({"output": dict(result.output), "complete": result.complete,
                           "continuation": None if result.continuation is None else dict(result.continuation)},
                          maximum_bytes=_MAX_CHUNK_BYTES)

    @staticmethod
    def _completion_digest(task: MaintenanceTask, result: MaintenanceResult) -> str:
        return _digest({
            "schema": "jeeves.local_maintenance_result.v1", "task_id": task.task_id,
            "attempt": task.attempt, "owner_id": task.owner_id,
            "fencing_token": task.fencing_token, "host_fencing_token": task.host_fencing_token,
            "continuation_id": task.continuation_id, "kind": task.kind.value,
            "source_digest": task.source_digest, "handler_version": task.handler_version,
            "output_digest": _digest(dict(result.output)), "complete": result.complete,
            "continuation_digest": None if result.continuation is None else _digest(dict(result.continuation)),
        })

    @staticmethod
    def _decode_result(raw: str, expected_digest: str) -> MaintenanceResult:
        if (not isinstance(raw, str) or len(raw.encode("utf-8")) > _MAX_CHUNK_BYTES
                or sha256(raw.encode("utf-8")).hexdigest() != expected_digest):
            raise IdleRuntimeError("maintenance chunk result proof diverged")
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {"output", "complete", "continuation"}:
                raise ValueError("invalid result envelope")
            return MaintenanceResult(**value)
        except (ValueError, TypeError, RecursionError) as exc:
            raise IdleRuntimeError("maintenance chunk result is malformed") from exc

    def _compact_chunks_locked(self) -> None:
        # Unacknowledged verified proofs and unverified completed work stay
        # durable. Only acknowledged/no-hook projections may be discarded.
        self._executor._db.execute(
            "DELETE FROM jeeves_idle_maintenance_chunk WHERE continuation_id IN "
            "(SELECT c.continuation_id FROM jeeves_idle_maintenance_chunk c "
            "WHERE c.ack_state IN ('acknowledged','not_required') AND NOT EXISTS "
            "(SELECT 1 FROM jeeves_idle_maintenance_task t WHERE t.task_id=c.task_id "
            "AND t.state IN ('ready','retry_wait','running') AND t.continuation_id=c.continuation_id) "
            "ORDER BY c.verified_at_ns,c.continuation_id LIMIT 32)",
        )
        self._executor._db.execute(
            "DELETE FROM jeeves_idle_maintenance_chunk WHERE continuation_id IN "
            "(SELECT c.continuation_id FROM jeeves_idle_maintenance_chunk c WHERE c.result_json IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM jeeves_idle_maintenance_task t WHERE t.task_id=c.task_id "
            "AND t.state IN ('ready','retry_wait','running')) ORDER BY c.recorded_at_ns LIMIT 32)",
        )

    def _prepare_chunk_locked(self, task: MaintenanceTask, now_ns: int,
                              policy: StudioMaintenancePolicy) -> MaintenanceResult | None:
        db = self._executor._db
        payload_digest = _digest(dict(task.payload))
        row = db.execute(
            "SELECT task_id,scope_id,source_digest,handler_version,payload_digest,result_json,result_digest "
            "FROM jeeves_idle_maintenance_chunk WHERE continuation_id=?", (task.continuation_id,),
        ).fetchone()
        identity = (task.task_id, task.scope_id, task.source_digest, task.handler_version, payload_digest)
        if row is not None:
            if row[:5] != identity:
                raise IdleRuntimeError("maintenance continuation changed its source or cursor")
            if row[5] is not None:
                return self._decode_result(row[5], row[6])
            db.execute(
                "UPDATE jeeves_idle_maintenance_chunk SET task_json=?,producer_owner_id=?,"
                "producer_attempt=?,producer_fence=? WHERE continuation_id=? AND result_json IS NULL",
                (self._task_json(task), task.owner_id, task.attempt, task.fencing_token, task.continuation_id),
            )
            return None
        self._compact_chunks_locked()
        count = db.execute("SELECT COUNT(*) FROM jeeves_idle_maintenance_chunk").fetchone()[0]
        if count >= policy.maximum_chunk_results:
            raise IdleWorkPreempted("chunk_result_backpressure")
        db.execute(
            "INSERT INTO jeeves_idle_maintenance_chunk "
            "(continuation_id,task_id,scope_id,source_digest,handler_version,payload_digest,task_json,"
            "recorded_at_ns,producer_owner_id,producer_attempt,producer_fence,ack_state,ack_failures,next_ack_ns) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,'unverified',0,0)",
            (task.continuation_id, *identity, self._task_json(task), now_ns,
             task.owner_id, task.attempt, task.fencing_token),
        )
        return None

    def _prepare_chunk(self, task: MaintenanceTask) -> MaintenanceResult | None:
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now = self._logical_now_locked(time_ns(), self._policy)
                if db.execute(
                    "SELECT 1 FROM jeeves_idle_maintenance_task WHERE task_id=? AND state='running' "
                    "AND owner_id=? AND attempts=? AND scope_fence=? AND host_fence=?",
                    (task.task_id, task.owner_id, task.attempt, task.fencing_token, task.host_fencing_token),
                ).fetchone() is None:
                    raise IdleRuntimeError("maintenance result admission lost its physical fence")
                result = self._prepare_chunk_locked(task, now, self._policy)
                db.execute("COMMIT")
                return result
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _record_chunk(self, task: MaintenanceTask, result: MaintenanceResult) -> None:
        raw = self._result_json(result)
        digest = sha256(raw.encode("utf-8")).hexdigest()
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now = self._logical_now_locked(time_ns(), self._policy)
                owned = db.execute(
                    "SELECT 1 FROM jeeves_idle_maintenance_task WHERE task_id=? AND state='running' "
                    "AND owner_id=? AND attempts=? AND scope_fence=? AND host_fence=?",
                    (task.task_id, task.owner_id, task.attempt, task.fencing_token, task.host_fencing_token),
                ).fetchone()
                if owned is None:
                    raise IdleRuntimeError("completed maintenance lost its physical custody")
                changed = db.execute(
                    "UPDATE jeeves_idle_maintenance_chunk SET result_json=?,result_digest=?,recorded_at_ns=? "
                    "WHERE continuation_id=? AND producer_owner_id=? AND producer_attempt=? "
                    "AND producer_fence=? AND result_json IS NULL",
                    (raw, digest, now, task.continuation_id, task.owner_id, task.attempt, task.fencing_token),
                ).rowcount
                if changed != 1:
                    raise IdleRuntimeError("maintenance chunk completion lost its reservation")
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _retry_acknowledgements(self, limit: int) -> int:
        """Retire already-verified local proofs; never re-enter a work handler."""
        if limit <= 0 or self._after_verified_chunk is None:
            return 0
        now = self._logical_now()
        with self._executor._lock:
            rows = self._executor._db.execute(
                "SELECT task_id,continuation_id,task_json,result_json,result_digest,verified_receipt_json,"
                "verified_receipt_digest,verified_intent_digest,ack_failures "
                "FROM jeeves_idle_maintenance_chunk WHERE ack_state='pending' AND next_ack_ns<=? "
                "ORDER BY next_ack_ns,verified_at_ns,continuation_id LIMIT ?", (now, limit),
            ).fetchall()
        for task_id, continuation, task_json, raw, digest, receipt_json, receipt_digest, intent, failures in rows:
            error: str | None = None
            try:
                item = json.loads(task_json)
                task = self._task_from_row(item, attempt=item["attempts"])
                result = self._decode_result(raw, digest)
                receipt_values = json.loads(receipt_json)
                receipt_values["kind"] = IdleWorkKind(receipt_values["kind"])
                receipt = HostIdleWorkReceipt(**receipt_values)
                if (task.task_id != task_id or receipt.digest != receipt_digest or task.continuation_id != continuation
                        or receipt.work_id != self._work_id(task.task_id, task.attempt)
                        or receipt.scope_id != task.scope_id or receipt.source_digest != task.source_digest
                        or receipt.kind is not task.kind or receipt.completed is not True
                        or receipt.host_worker_id != task.owner_id
                        or receipt.output_digest != _digest(dict(result.output))
                        or receipt.external_event_digest != self._completion_digest(task, result)):
                    raise IdleRuntimeError("verified maintenance acknowledgement proof diverged")
                with self._executor._lock:
                    verified = self._executor._db.execute(
                        "SELECT state,receipt_digest FROM jeeves_idle_effect WHERE intent_digest=?", (intent,),
                    ).fetchone()
                if verified != (IdleExecutionState.VERIFIED.value, receipt_digest):
                    raise IdleRuntimeError("maintenance acknowledgement lacks verified effect custody")
                # Host callback is bounded, local and idempotent. It runs after
                # commit with no persistence lock, foreground lock or worker.
                acknowledgement = self._after_verified_chunk(task, result, receipt)
                if isinstance(acknowledgement, Mapping) and acknowledgement.get("acknowledged") is False:
                    raise IdleRuntimeError("host did not acknowledge verified maintenance")
            except Exception as exc:
                error = type(exc).__name__[:96]
            with self._executor._lock:
                db = self._executor._db
                try:
                    db.execute("BEGIN IMMEDIATE")
                    if error is None:
                        changed = db.execute(
                            "UPDATE jeeves_idle_maintenance_chunk SET ack_state='acknowledged',"
                            "last_ack_error=NULL WHERE continuation_id=? AND ack_state='pending' "
                            "AND verified_receipt_digest=?", (continuation, receipt_digest),
                        ).rowcount
                        if changed == 1:
                            self._event(task_id, "chunk_acknowledged", now,
                                        {"continuation_id": continuation, "verified_receipt_digest": receipt_digest})
                    else:
                        failures = min(1_000_000, failures + 1)
                        backoff = min(self._policy.maximum_backoff_ms,
                                      self._policy.initial_backoff_ms * 2 ** min(failures - 1, 20))
                        db.execute(
                            "UPDATE jeeves_idle_maintenance_chunk SET ack_failures=?,next_ack_ns=?,"
                            "last_ack_error=? WHERE continuation_id=? AND ack_state='pending' "
                            "AND verified_receipt_digest=?",
                            (failures, now + backoff * 1_000_000, error, continuation, receipt_digest),
                        )
                        self._event(task_id, "chunk_acknowledgement_deferred", now,
                                    {"continuation_id": continuation, "error": error, "failures": failures})
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:
                        db.execute("ROLLBACK")
                    raise
        return len(rows)

    def enqueue(
        self, *, kind: IdleWorkKind, scope_id: str, source_digest: str,
        idempotency_key: str, payload: Mapping[str, Any] | None = None,
        priority: int = 50,
    ) -> dict[str, Any]:
        if not isinstance(kind, IdleWorkKind) or kind not in self._handlers:
            raise IdleRuntimeError("maintenance kind has no host-owned local handler")
        _identifier(scope_id, "scope")
        _identifier(idempotency_key, "idempotency key")
        _sha(source_digest)
        if type(priority) is not int or not 0 <= priority <= 100:
            raise IdleRuntimeError("maintenance priority must be 0..100")
        if payload is not None and not isinstance(payload, Mapping):
            raise IdleRuntimeError("maintenance payload must be an object")
        raw = _canonical(dict(payload or {}))
        payload_digest = sha256(raw.encode("utf-8")).hexdigest()
        task_id = _digest({"scope_id": scope_id, "kind": kind.value,
                           "idempotency_key": idempotency_key})
        _, wall_ns = self._now()
        with self._state_lock:
            if self._closed or self._closing:
                raise IdleRuntimeError("maintenance controller is closing")
            policy = self._policy
        with self._executor._lock:
            if self._closing or self._closed or self._executor._closed:
                raise IdleRuntimeError("maintenance controller is closing")
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now_ns = self._logical_now_locked(wall_ns, policy)
                row = db.execute(
                    "SELECT source_digest,payload_digest,state FROM "
                    "jeeves_idle_maintenance_task WHERE task_id=?", (task_id,),
                ).fetchone()
                if row is not None:
                    if row[:2] != (source_digest, payload_digest):
                        raise IdleRuntimeError("maintenance idempotency key changed its source or payload")
                    db.execute("COMMIT")
                    return {"task_id": task_id, "state": row[2], "deduplicated": True}
                # Completed task projections may be compacted, but the first
                # attempt's authoritative receipt permanently fences replay.
                retained = db.execute(
                    "SELECT source_digest FROM jeeves_idle_effect WHERE work_id=?",
                    (self._work_id(task_id, 1),),
                ).fetchone()
                if retained is not None:
                    if retained[0] != source_digest:
                        raise IdleRuntimeError("retained maintenance identity changed source")
                    db.execute("COMMIT")
                    return {"task_id": task_id, "state": "retained", "deduplicated": True}
                self._compact_terminal(policy.maximum_retained_tasks)
                queued = db.execute(
                    "SELECT COUNT(*) FROM jeeves_idle_maintenance_task "
                    "WHERE state IN ('ready','running','retry_wait')",
                ).fetchone()[0]
                if queued >= policy.maximum_queue:
                    raise IdleRuntimeError("maintenance queue has reached its host budget")
                scope_queued = db.execute(
                    "SELECT COUNT(*) FROM jeeves_idle_maintenance_task "
                    "WHERE scope_id=? AND state IN ('ready','running','retry_wait')", (scope_id,),
                ).fetchone()[0]
                if scope_queued >= min(policy.maximum_queue, policy.maximum_scope_queue):
                    raise IdleRuntimeError("maintenance scope has reached its fair queue budget")
                version = self._handlers[kind].version
                continuation = _digest({"task_id": task_id, "source_digest": source_digest,
                                        "handler_version": version, "index": 0,
                                        "cursor_digest": payload_digest})
                record = {
                    "task_id": task_id, "scope_id": scope_id, "kind": kind.value,
                    "source_digest": source_digest, "payload_digest": payload_digest,
                    "payload_json": raw, "priority": priority, "state": "ready",
                    "attempts": 0, "failures": 0, "next_run_ns": now_ns,
                    "created_at_ns": now_ns, "updated_at_ns": now_ns, "lease_until_ns": 0,
                    "last_error": None, "last_intent": None, "output_digest": None,
                    "owner_id": None, "host_id": None, "host_fence": 0, "scope_fence": 0,
                    "heartbeat_ns": 0, "drained_at_ns": None, "continuation_index": 0,
                    "continuation_id": continuation, "handler_version": version,
                }
                db.execute(
                    "INSERT INTO jeeves_idle_maintenance_task (" + ",".join(record)
                    + ") VALUES (" + ",".join("?" for _ in record) + ")", tuple(record.values()),
                )
                self._event(task_id, "enqueued", now_ns,
                            {"kind": kind.value, "scope_id": scope_id,
                             "source_digest": source_digest, "priority": priority})
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {"task_id": task_id, "state": "ready", "deduplicated": False}

    def retry_failed(self, *, task_id: str, scope_id: str,
                     source_digest: str, expected_attempts: int) -> dict[str, Any]:
        """Host-only recovery proposal; normal idle admission still owns effects.

        The caller must authorize the exact scoped source. This never invokes a
        handler or acknowledges an ambiguous outcome, and it preserves the
        repeat-safe continuation identity and any completed chunk result.
        """
        _sha(task_id)
        _sha(source_digest)
        _identifier(scope_id, "retry scope")
        if type(expected_attempts) is not int or not 0 <= expected_attempts <= 1_000_000:
            raise IdleRuntimeError("host retry requires the observed attempt count")
        with self._state_lock:
            if self._closed or self._closing:
                raise IdleRuntimeError("maintenance controller is closing")
            policy = self._policy
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now = self._logical_now_locked(time_ns(), policy)
                row = db.execute(
                    f"SELECT {_TASK_COLUMNS} FROM jeeves_idle_maintenance_task "
                    "WHERE task_id=? AND scope_id=? AND source_digest=?",
                    (task_id, scope_id, source_digest),
                ).fetchone()
                if row is None:
                    raise IdleRuntimeError("no retained maintenance task matches the host retry source")
                item = dict(zip(_TASK_COLUMNS.split(","), row))
                if item["attempts"] != expected_attempts:
                    raise IdleRuntimeError("maintenance attempt count changed before host retry")
                if item["state"] in ("ready", "retry_wait"):
                    db.execute("COMMIT")
                    return {"task_id": task_id, "source_digest": source_digest,
                            "state": item["state"], "attempts": item["attempts"], "deduplicated": True}
                if item["state"] != "failed":
                    raise IdleRuntimeError("host retry requires a failed, physically drained task")
                if expected_attempts >= 1_000_000:
                    raise IdleRuntimeError("maintenance attempt budget exhausted; a new task is required")
                kind = IdleWorkKind(item["kind"])
                handler = self._handlers.get(kind)
                if handler is None or item["handler_version"] != handler.version:
                    raise IdleRuntimeError("maintenance handler changed; a new source-bound task is required")
                held = db.execute(
                    "SELECT 1 FROM jeeves_idle_maintenance_lease WHERE task_id=? AND state='held'", (task_id,),
                ).fetchone()
                if held is not None:
                    raise IdleRuntimeError("failed maintenance still holds physical custody")
                if (item["attempts"] > 0 and item["drained_at_ns"] is None
                        and not self._owner_drained(item["owner_id"])):
                    raise IdleRuntimeError("failed maintenance lacks physical drain proof")
                queued = db.execute(
                    "SELECT COUNT(*) FROM jeeves_idle_maintenance_task "
                    "WHERE state IN ('ready','retry_wait','running')",
                ).fetchone()[0]
                scoped = db.execute(
                    "SELECT COUNT(*) FROM jeeves_idle_maintenance_task WHERE scope_id=? "
                    "AND state IN ('ready','retry_wait','running')", (scope_id,),
                ).fetchone()[0]
                if (queued >= policy.maximum_queue
                        or scoped >= min(policy.maximum_queue, policy.maximum_scope_queue)):
                    raise IdleRuntimeError("maintenance retry exceeds the host or scope queue budget")
                db.execute(
                    "UPDATE jeeves_idle_maintenance_task SET state='ready',failures=0,"
                    "next_run_ns=?,updated_at_ns=?,last_error=NULL,drained_at_ns=COALESCE(drained_at_ns,?) "
                    "WHERE task_id=? AND state='failed' AND attempts=?",
                    (now, now, now, task_id, expected_attempts),
                )
                retained = db.execute(
                    "SELECT 1 FROM jeeves_idle_maintenance_chunk WHERE continuation_id=? "
                    "AND result_json IS NOT NULL", (item["continuation_id"],),
                ).fetchone() is not None
                self._event(task_id, "host_retry_queued", now,
                            {"scope_id": scope_id, "source_digest": source_digest,
                             "continuation_id": item["continuation_id"], "retained_result": retained})
                db.execute("COMMIT")
                return {"task_id": task_id, "source_digest": source_digest, "state": "ready",
                        "attempts": item["attempts"], "deduplicated": False,
                        "retained_result": retained}
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _compact_terminal(self, retained: int) -> None:
        # These are bounded local queue projections. Any attempt that entered
        # a handler keeps its first authoritative effect claim as a permanent
        # replay fence. Denied tasks have no effect to replay. No authoritative
        # jeeves_idle_effect/event row is ever compacted here.
        self._executor._db.execute(
            "DELETE FROM jeeves_idle_maintenance_task WHERE task_id IN "
            "(SELECT task_id FROM jeeves_idle_maintenance_task "
            "WHERE state IN ('completed','failed') "
            "ORDER BY updated_at_ns DESC,task_id LIMIT -1 OFFSET ?)", (retained,),
        )
        self._compact_chunks_locked()
        # Drained process presence is operational state. Keep every live or
        # unresolved reference and all immutable effect receipts separately.
        self._executor._db.execute(
            "DELETE FROM jeeves_idle_maintenance_owner WHERE owner_id IN "
            "(SELECT o.owner_id FROM jeeves_idle_maintenance_owner o WHERE o.state='drained' "
            "AND o.owner_id!=? AND NOT EXISTS (SELECT 1 FROM jeeves_idle_maintenance_lease l "
            "WHERE l.owner_id=o.owner_id AND l.state='held') AND NOT EXISTS "
            "(SELECT 1 FROM jeeves_idle_maintenance_task t WHERE t.owner_id=o.owner_id "
            "AND t.state IN ('ready','retry_wait','running')) AND NOT EXISTS "
            "(SELECT 1 FROM jeeves_idle_maintenance_chunk c WHERE c.producer_owner_id=o.owner_id "
            "AND c.ack_state IN ('pending','unverified')) ORDER BY o.heartbeat_ns LIMIT 32)",
            (self._identity["owner_id"],),
        )

    def _claim(self, now_ns: int, policy: StudioMaintenancePolicy) -> MaintenanceTask | None:
        allowed = tuple(kind.value for kind in self._handlers
                        if policy.augmentation_enabled
                        or kind is not IdleWorkKind.ELIGIBLE_AUGMENTATION)
        if not allowed:
            return None
        placeholders = ",".join("?" for _ in allowed)
        with self._executor._lock:
            if self._executor._closed:
                raise IdleRuntimeError("maintenance executor is closed")
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                now_ns = self._logical_now_locked(now_ns, policy)
                # Timeouts cannot prove physical completion. A paused process
                # retains custody until its worker drains or the host proves
                # its process/boot/start identity no longer exists.
                expired = db.execute(
                    f"SELECT {_TASK_COLUMNS} FROM jeeves_idle_maintenance_task "
                    "WHERE state='running' AND lease_until_ns<=? "
                    "ORDER BY CASE WHEN host_id=? THEN 0 ELSE 1 END,"
                    "recovery_checked_ns,updated_at_ns,task_id LIMIT ?",
                    (now_ns, self._identity["host_id"], min(32, policy.maximum_queue)),
                ).fetchall()
                blocked = False
                for expired_row in expired:
                    stale = dict(zip(_TASK_COLUMNS.split(","), expired_row))
                    task_id = stale["task_id"]
                    db.execute(
                        "UPDATE jeeves_idle_maintenance_task SET recovery_checked_ns=? WHERE task_id=?",
                        (now_ns, task_id),
                    )
                    if not self._owner_drained(stale["owner_id"]):
                        blocked = True
                        if stale["last_error"] != "recovery_blocked_owner_alive_or_unknown":
                            db.execute(
                                "UPDATE jeeves_idle_maintenance_task SET "
                                "last_error='recovery_blocked_owner_alive_or_unknown' "
                                "WHERE task_id=? AND state='running' AND attempts=?",
                                (task_id, stale["attempts"]),
                            )
                            self._event(task_id, "recovery_blocked", now_ns,
                                        {"owner_id": stale["owner_id"], "drain_confirmed": False})
                        continue
                    if stale["owner_id"] is not None and stale["scope_fence"]:
                        stale_task = self._task_from_row(stale, attempt=stale["attempts"])
                        self._release_drained_resources_locked(stale_task, now_ns)
                    db.execute(
                        "UPDATE jeeves_idle_maintenance_task SET state='retry_wait',"
                        "next_run_ns=?,updated_at_ns=?,lease_until_ns=0,"
                        "drained_at_ns=?,last_error='interrupted_local_chunk',owner_id=NULL,"
                        "host_id=NULL,host_fence=0,scope_fence=0 WHERE task_id=? "
                        "AND state='running' AND attempts=?",
                        (now_ns + policy.preemption_backoff_ms * 1_000_000, now_ns,
                         now_ns, task_id, stale["attempts"]),
                    )
                    self._event(task_id, "local_chunk_recovered", now_ns,
                                {"authority": "host-confirmed-physical-drain", "prior_owner_id": stale["owner_id"]})
                if not self._host_idle_locked(now_ns):
                    self._last_reason = "host_foreground_preemption"
                    db.execute("COMMIT")
                    return None
                rows = db.execute(
                    f"SELECT {_TASK_COLUMNS} FROM jeeves_idle_maintenance_task t "
                    f"WHERE state IN ('ready','retry_wait') AND next_run_ns<=? "
                    f"AND kind IN ({placeholders}) AND NOT EXISTS "
                    "(SELECT 1 FROM jeeves_idle_maintenance_circuit c "
                    "WHERE c.scope_id=t.scope_id AND c.kind=t.kind AND c.open_until_ns>?) "
                    "ORDER BY MIN(100,priority+MAX(0,(?-updated_at_ns)/?)) DESC,"
                    "updated_at_ns,created_at_ns,task_id LIMIT 32",
                    (now_ns, *allowed, now_ns, now_ns, policy.priority_aging_ms * 1_000_000),
                ).fetchall()
                lease_ns = (policy.maximum_chunk_wall_ms
                            + policy.interrupted_lease_grace_ms) * 1_000_000
                self._last_reason = "recovery_blocked" if blocked else "idle"
                for row in rows:
                    item = dict(zip(_TASK_COLUMNS.split(","), row))
                    version = self._handlers[IdleWorkKind(item["kind"])].version
                    if item["handler_version"] not in ("", version):
                        db.execute(
                            "UPDATE jeeves_idle_maintenance_task SET state='failed',"
                            "last_error='handler_version_changed',updated_at_ns=? WHERE task_id=?",
                            (now_ns, item["task_id"]),
                        )
                        continue
                    db.execute("SAVEPOINT maintenance_candidate")
                    host_fence = self._acquire_resource_locked(
                        "host:" + self._identity["host_id"], None, item["task_id"], now_ns, lease_ns,
                    )
                    if host_fence is None:
                        db.execute("ROLLBACK TO maintenance_candidate")
                        db.execute("RELEASE maintenance_candidate")
                        self._last_reason = "recovery_blocked" if blocked else "lease_contended"
                        break
                    scope_fence = self._acquire_resource_locked(
                        "scope:" + item["scope_id"], item["scope_id"], item["task_id"], now_ns, lease_ns,
                    )
                    if scope_fence is None:
                        db.execute("ROLLBACK TO maintenance_candidate")
                        db.execute("RELEASE maintenance_candidate")
                        self._last_reason = "lease_contended"
                        continue
                    item.update(owner_id=self._identity["owner_id"], host_id=self._identity["host_id"],
                                host_fence=host_fence, scope_fence=scope_fence, handler_version=version)
                    if item["continuation_id"] is None:
                        item["continuation_id"] = _digest({
                            "task_id": item["task_id"], "source_digest": item["source_digest"],
                            "handler_version": version, "index": item["continuation_index"],
                            "cursor_digest": _digest(json.loads(item["payload_json"])),
                        })
                    task = self._task_from_row(item, attempt=item["attempts"] + 1)
                    self._compact_chunks_locked()
                    has_chunk = db.execute(
                        "SELECT 1 FROM jeeves_idle_maintenance_chunk WHERE continuation_id=?",
                        (task.continuation_id,),
                    ).fetchone() is not None
                    if (not has_chunk and db.execute(
                        "SELECT COUNT(*) FROM jeeves_idle_maintenance_chunk",
                    ).fetchone()[0] >= policy.maximum_chunk_results):
                        db.execute("ROLLBACK TO maintenance_candidate")
                        db.execute("RELEASE maintenance_candidate")
                        self._last_reason = "result_backpressure"
                        continue
                    changed = db.execute(
                        "UPDATE jeeves_idle_maintenance_task SET state='running',attempts=?,"
                        "updated_at_ns=?,lease_until_ns=?,heartbeat_ns=?,owner_id=?,host_id=?,"
                        "host_fence=?,scope_fence=?,drained_at_ns=NULL,continuation_id=?,handler_version=? "
                        "WHERE task_id=? AND state IN ('ready','retry_wait') AND attempts=?",
                        (task.attempt, now_ns, now_ns + lease_ns, now_ns, task.owner_id, task.host_id,
                         host_fence, scope_fence, task.continuation_id, version, task.task_id, item["attempts"]),
                    ).rowcount
                    if changed != 1:
                        raise IdleRuntimeError("maintenance claim lost its compare-and-swap")
                    self._prepare_chunk_locked(task, now_ns, policy)
                    db.execute(
                        "UPDATE jeeves_idle_maintenance_owner SET physical_tasks=1,heartbeat_ns=? "
                        "WHERE owner_id=? AND state='live'", (now_ns, task.owner_id),
                    )
                    self._event(task.task_id, "chunk_claimed", now_ns,
                                {"attempt": task.attempt, "lease_until_ns": now_ns + lease_ns,
                                 "owner_id": task.owner_id, "host_fencing_token": host_fence,
                                 "fencing_token": scope_fence, "continuation_id": task.continuation_id})
                    db.execute("RELEASE maintenance_candidate")
                    db.execute("COMMIT")
                    return task
                if blocked and not rows:
                    self._last_reason = "recovery_blocked"
                db.execute("COMMIT")
                return None
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _task_from_row(item: Mapping[str, Any], *, attempt: int) -> MaintenanceTask:
        try:
            kind = IdleWorkKind(item["kind"])
            payload = json.loads(item["payload_json"])
            if kind not in LOCAL_MAINTENANCE_KINDS or not isinstance(payload, dict):
                raise ValueError("invalid local task")
            _sha(item["task_id"])
            _sha(item["source_digest"])
            _identifier(item["scope_id"], "scope")
            _canonical(payload)
            if type(attempt) is not int or not 1 <= attempt <= 1_000_000:
                raise ValueError("attempt budget exceeded")
            if type(item["priority"]) is not int or not 0 <= item["priority"] <= 100:
                raise ValueError("invalid priority")
            if type(item["created_at_ns"]) is not int or item["created_at_ns"] < 0:
                raise ValueError("invalid creation timestamp")
            _identifier(item["owner_id"], "owner")
            _identifier(item["host_id"], "host")
            _sha(item["continuation_id"])
            _identifier(item["handler_version"], "handler version")
            for key in ("host_fence", "scope_fence"):
                if type(item[key]) is not int or not 1 <= item[key] <= 9_000_000_000_000_000:
                    raise ValueError("invalid ownership fence")
            if (type(item["continuation_index"]) is not int
                    or not 0 <= item["continuation_index"] <= 1_000_000):
                raise ValueError("invalid continuation index")
            if item["continuation_id"] != _digest({
                "task_id": item["task_id"], "source_digest": item["source_digest"],
                "handler_version": item["handler_version"], "index": item["continuation_index"],
                "cursor_digest": _digest(payload),
            }):
                raise ValueError("continuation identity diverged from its exact cursor")
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise IdleRuntimeError("invalid persisted maintenance task") from exc
        return MaintenanceTask(
            task_id=item["task_id"], scope_id=item["scope_id"], kind=kind,
            source_digest=item["source_digest"], payload=MappingProxyType(payload),
            attempt=attempt, priority=item["priority"], created_at_ns=item["created_at_ns"],
            owner_id=item["owner_id"], host_id=item["host_id"],
            fencing_token=item["scope_fence"], host_fencing_token=item["host_fence"],
            continuation_index=item["continuation_index"], continuation_id=item["continuation_id"],
            handler_version=item["handler_version"],
        )

    def _finish(
        self, task: MaintenanceTask, *, now_ns: int, policy: StudioMaintenancePolicy,
        state: str, reason: str | None, intent: str | None = None,
        result: MaintenanceResult | None = None,
        receipt: HostIdleWorkReceipt | None = None,
    ) -> None:
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT attempts,failures FROM jeeves_idle_maintenance_task "
                    "WHERE task_id=? AND state='running' AND owner_id=? AND scope_fence=? "
                    "AND host_fence=? AND continuation_id=?",
                    (task.task_id, task.owner_id, task.fencing_token,
                     task.host_fencing_token, task.continuation_id),
                ).fetchone()
                if current is None or current[0] != task.attempt:
                    raise IdleRuntimeError("maintenance chunk lost its durable lease")
                if intent is None:
                    # invoke_one may raise after its durable claim. Link that
                    # exact claim rather than losing partial-effect custody in
                    # the queue's interruption/backoff projection.
                    claimed = db.execute(
                        "SELECT intent_digest FROM jeeves_idle_effect WHERE work_id=?",
                        (self._work_id(task.task_id, task.attempt),),
                    ).fetchone()
                    if claimed is not None:
                        intent = claimed[0]
                failures = current[1]
                next_run_ns = now_ns
                output_digest = None if result is None else _digest(dict(result.output))
                if state == "failed":
                    failures += 1
                    if failures < policy.maximum_consecutive_failures:
                        state = "retry_wait"
                    backoff_ms = min(policy.maximum_backoff_ms,
                                     policy.initial_backoff_ms * 2 ** min(failures - 1, 20))
                    # Stable jitter prevents cohorts from hammering the same DB.
                    jitter = int(task.task_id[:8], 16) % max(1, backoff_ms // 5)
                    next_run_ns += (backoff_ms + jitter) * 1_000_000
                    previous = db.execute(
                        "SELECT failures FROM jeeves_idle_maintenance_circuit "
                        "WHERE scope_id=? AND kind=?", (task.scope_id, task.kind.value),
                    ).fetchone()
                    circuit_failures = 1 if previous is None else previous[0] + 1
                    open_until = (now_ns + policy.circuit_cooldown_ms * 1_000_000
                                  if circuit_failures >= policy.circuit_failure_threshold else 0)
                    db.execute(
                        "INSERT INTO jeeves_idle_maintenance_circuit VALUES (?,?,?,?,?) "
                        "ON CONFLICT(scope_id,kind) DO UPDATE SET failures=excluded.failures,"
                        "open_until_ns=excluded.open_until_ns,last_error=excluded.last_error",
                        (task.scope_id, task.kind.value, circuit_failures, open_until, reason),
                    )
                elif state == "retry_wait":
                    next_run_ns += policy.preemption_backoff_ms * 1_000_000
                elif state == "completed":
                    if result is None or receipt is None or intent is None:
                        raise IdleRuntimeError("completed chunk requires its verified result and receipt")
                    custody = db.execute(
                        "SELECT state,receipt_digest,work_id,source_digest FROM jeeves_idle_effect "
                        "WHERE intent_digest=?", (intent,),
                    ).fetchone()
                    if custody != (IdleExecutionState.VERIFIED.value, receipt.digest,
                                    self._work_id(task.task_id, task.attempt), task.source_digest):
                        raise IdleRuntimeError("maintenance cursor cannot advance without verified effect custody")
                    result_digest = sha256(self._result_json(result).encode("utf-8")).hexdigest()
                    admitted = db.execute(
                        "UPDATE jeeves_idle_maintenance_chunk SET verified_intent_digest=?,"
                        "verified_receipt_json=?,verified_receipt_digest=?,verified_at_ns=?,ack_state=?,"
                        "next_ack_ns=?,task_json=? WHERE continuation_id=? AND result_digest=?",
                        (intent, _canonical(asdict(receipt), maximum_bytes=_MAX_OUTPUT_BYTES),
                         receipt.digest, now_ns, "pending" if self._after_verified_chunk is not None else "not_required",
                         now_ns, self._task_json(task), task.continuation_id, result_digest),
                    ).rowcount
                    if admitted != 1:
                        raise IdleRuntimeError("maintenance cursor lost its durable chunk result")
                    failures = 0
                    db.execute(
                        "DELETE FROM jeeves_idle_maintenance_circuit WHERE scope_id=? AND kind=?",
                        (task.scope_id, task.kind.value),
                    )
                    if result is not None and not result.complete:
                        state = "ready"
                        cursor = dict(task.payload if result.continuation is None else result.continuation)
                        index = task.continuation_index + 1
                        if index > 1_000_000:
                            raise IdleRuntimeError("maintenance continuation budget exhausted")
                        continuation = _digest({
                            "task_id": task.task_id, "source_digest": task.source_digest,
                            "handler_version": task.handler_version, "index": index,
                            "cursor_digest": _digest(cursor),
                        })
                        # Initial payload_digest keeps enqueue idempotency;
                        # each verified cursor has its own repeat-safe identity.
                        db.execute(
                            "UPDATE jeeves_idle_maintenance_task SET payload_json=?,"
                            "continuation_index=?,continuation_id=? WHERE task_id=?",
                            (_canonical(cursor), index, continuation, task.task_id),
                        )
                db.execute(
                    "UPDATE jeeves_idle_maintenance_task SET state=?,failures=?,next_run_ns=?,"
                    "updated_at_ns=?,lease_until_ns=0,heartbeat_ns=?,drained_at_ns=?,"
                    "last_error=?,last_intent=?,output_digest=? "
                    "WHERE task_id=? AND attempts=? AND owner_id=? AND scope_fence=? AND host_fence=?",
                    (state, failures, next_run_ns, now_ns, now_ns, now_ns, reason, intent, output_digest,
                     task.task_id, task.attempt, task.owner_id, task.fencing_token, task.host_fencing_token),
                )
                self._release_resources_locked(task, now_ns)
                db.execute(
                    "UPDATE jeeves_idle_maintenance_owner SET physical_tasks=0,heartbeat_ns=? "
                    "WHERE owner_id=?", (now_ns, task.owner_id),
                )
                self._event(task.task_id, "chunk_" + state, now_ns,
                            {"attempt": task.attempt, "state": state, "reason": reason,
                             "intent_digest": intent, "output_digest": output_digest,
                             "next_run_ns": next_run_ns, "failures": failures,
                             "owner_id": task.owner_id, "fencing_token": task.fencing_token,
                             "continuation_id": task.continuation_id, "physical_drained": True})
                self._compact_terminal(policy.maximum_retained_tasks)
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def tick(self) -> dict[str, Any]:
        """Execute at most a configured number of cooperative bounded chunks."""
        if not self._tick_lock.acquire(blocking=False):
            return {"state": "busy", "processed": 0}
        processed = 0
        started = monotonic_ns()
        try:
            if not self.heartbeat():
                return {"state": "closed", "processed": 0}
            acknowledgements = self._retry_acknowledgements(self._policy.maximum_ack_retries_per_tick)
            with self._state_lock:
                policy = self._policy
                generation = self._foreground_generation
            if self._preempted(generation):
                with self._state_lock:
                    reason = ("disabled" if not policy.enabled else "coordination_unavailable"
                              if self._coordination_fault is not None else "foreground_preemption")
                    self._last_reason = reason
                return {"state": reason, "processed": 0}
            for _ in range(policy.maximum_tasks_per_tick):
                if self._preempted(generation):
                    break
                if (monotonic_ns() - started
                        > policy.maximum_chunk_wall_ms * policy.maximum_tasks_per_tick * 1_000_000):
                    break
                telemetry, now_ns = self._now()
                # Check telemetry before claiming a task, so pressure does not
                # churn attempts or consume retry failure budgets.
                gate = IdleWorkCandidate(
                    work_id="maintenance-admission", scope_id="host-maintenance",
                    source_digest=telemetry.host_observation_digest,
                    kind=next(iter(self._handlers)), relevance_ppm=0,
                    novelty_ppm=0, evidence_confidence_ppm=1_000_000,
                    created_at_ns=now_ns, cost_units=1,
                )
                admission = JeevesIdleLearningScheduler(policy=self._executor.policy).propose(
                    (gate,), telemetry, host_now_ns=now_ns,
                )
                if not admission.assignments:
                    with self._state_lock:
                        self._last_reason = admission.plan_reason
                    break
                task = self._claim(now_ns, policy)
                if task is None:
                    with self._state_lock:
                        if self._last_reason not in ("lease_contended", "recovery_blocked", "host_foreground_preemption", "result_backpressure"):
                            self._last_reason = "idle"
                    break
                with self._state_lock:
                    self._active_tasks = 1
                    self._last_run_ns = now_ns
                    self._last_reason = "running"
                context = _AttemptContext(task, self._handlers[task.kind], controller=self)
                candidate = IdleWorkCandidate(
                    work_id=self._work_id(task.task_id, task.attempt),
                    scope_id=task.scope_id, source_digest=task.source_digest,
                    kind=task.kind, relevance_ppm=task.priority * 10_000,
                    novelty_ppm=0, evidence_confidence_ppm=1_000_000,
                    created_at_ns=min(task.created_at_ns, now_ns), cost_units=1,
                )
                intent: str | None = None
                try:
                    plan = JeevesIdleLearningScheduler(policy=self._executor.policy).propose(
                        (candidate,), telemetry, host_now_ns=now_ns,
                    )
                    if not plan.assignments:
                        raise IdleWorkPreempted(plan.plan_reason)
                    state, intent = self._executor.invoke_one(
                        plan=plan, assignment=plan.assignments[0], candidate=candidate,
                        telemetry=telemetry, host_now_ns=now_ns, context=context,
                        budget=IdleWorkBudget(
                            maximum_wall_ns=policy.maximum_chunk_wall_ms * 1_000_000,
                            maximum_cpu_ns=policy.maximum_chunk_cpu_ms * 1_000_000,
                            maximum_polls=policy.maximum_chunk_polls,
                            maximum_memory_drop_ppm=policy.maximum_memory_drop_ppm,
                        ),
                        stop_requested=lambda: self._preempted(generation)
                        or not self._heartbeat_task(task, policy),
                    )
                    if state is not IdleExecutionState.VERIFIED:
                        raise IdleWorkPreempted("chunk_idle_compliance_unconfirmed")
                    self._finish(task, now_ns=self._completion_time(now_ns), policy=policy,
                                 state="completed", reason=None, intent=intent,
                                 result=context.output, receipt=context.receipt)
                    processed += 1
                except IdleWorkPreempted as exc:
                    self._finish(task, now_ns=self._completion_time(now_ns), policy=policy,
                                 state="retry_wait", reason=str(exc)[:128], intent=intent,
                                 result=context.output)
                    with self._state_lock:
                        self._last_reason = "preempted"
                    break
                except Exception as exc:
                    # Exception text may contain tenant data or filesystem
                    # locations; the bounded class name is sufficient to act on.
                    self._finish(task, now_ns=self._completion_time(now_ns), policy=policy,
                                 state="failed", reason=type(exc).__name__[:96], intent=intent)
                    with self._state_lock:
                        self._last_reason = "handler_failed"
                    break
                finally:
                    with self._state_lock:
                        self._active_tasks = 0
            # Acknowledgement failures cannot enter the chunk failure handler:
            # the verified effect and advanced cursor have already committed.
            self._retry_acknowledgements(max(0, policy.maximum_ack_retries_per_tick - acknowledgements))
            with self._state_lock:
                if self._last_reason == "running":
                    self._last_reason = "idle"
                reason = self._last_reason
            return {"state": reason, "processed": processed}
        finally:
            self._tick_lock.release()

    def _completion_time(self, prior_ns: int) -> int:
        try:
            return self._logical_now()
        except Exception:
            # Receipt custody still commits if host telemetry becomes
            # unavailable after the chunk. No further work will be admitted.
            return self._last_logical_ns or prior_ns

    def snapshot(self, *, limit: int = 20, scope_id: str | None = None) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise IdleRuntimeError("maintenance snapshot page must be 1..100")
        if scope_id is not None:
            _identifier(scope_id, "snapshot scope")
        with self._state_lock:
            policy = self._policy.to_dict()
            status = {
                "state": ("closed" if self._closed else "disabled" if not policy["enabled"]
                          else "running" if self._active_tasks else self._last_reason),
                "active_tasks": self._active_tasks,
                "foreground_requests": self._foreground_requests,
                "last_run_ns": self._last_run_ns,
                "last_reason": self._last_reason,
                "next_run_ns": None,
                "coordination_state": "synchronized" if self._coordination_fault is None else "unavailable",
                "coordination_error": self._coordination_fault,
            }
            closed = self._closed
        if closed:
            return {"schema": "jeeves.studio_maintenance.v1", "policy": policy,
                    "status": status, "queued_tasks": 0, "recent_tasks": [],
                    "circuits": [], "execution_authority": "host-local-derived-only"}
        with self._executor._lock:
            if self._executor._closed:
                status["state"] = "closed"
                return {"schema": "jeeves.studio_maintenance.v1", "policy": policy,
                        "status": status, "queued_tasks": 0, "recent_tasks": [],
                        "circuits": [], "execution_authority": "host-local-derived-only"}
            db = self._executor._db
            scope_clause = "" if scope_id is None else " WHERE scope_id=?"
            scope_params: tuple[Any, ...] = () if scope_id is None else (scope_id,)
            rows = db.execute(
                "SELECT task_id,scope_id,source_digest,kind,state,priority,attempts,failures,"
                "next_run_ns,updated_at_ns,last_error,output_digest,owner_id,host_id,"
                "scope_fence,host_fence,continuation_index,continuation_id,heartbeat_ns,"
                "lease_until_ns,drained_at_ns,handler_version "
                "FROM jeeves_idle_maintenance_task" + scope_clause
                + " ORDER BY updated_at_ns DESC,task_id LIMIT ?",
                (*scope_params, limit),
            ).fetchall()
            keys = ("task_id", "scope_id", "source_digest", "kind", "state", "priority", "attempts", "failures",
                    "next_run_ns", "updated_at_ns", "last_error", "output_digest", "owner_id", "host_id",
                    "fencing_token", "host_fencing_token", "continuation_index", "continuation_id",
                    "heartbeat_ns", "lease_until_ns", "drained_at_ns", "handler_version")
            queued, next_run = db.execute(
                "SELECT COUNT(*),MIN(next_run_ns) FROM jeeves_idle_maintenance_task "
                "WHERE state IN ('ready','running','retry_wait')"
                + ("" if scope_id is None else " AND scope_id=?"), scope_params,
            ).fetchone()
            circuits = db.execute(
                "SELECT scope_id,kind,failures,open_until_ns,last_error "
                "FROM jeeves_idle_maintenance_circuit" + scope_clause
                + " ORDER BY open_until_ns DESC LIMIT ?", (*scope_params, limit),
            ).fetchall()
            status["next_run_ns"] = next_run
            head = self._executor.history_head()
            owner = db.execute(
                "SELECT owner_id,host_id,state,heartbeat_ns,foreground_requests,physical_tasks "
                "FROM jeeves_idle_maintenance_owner WHERE owner_id=?", (self._identity["owner_id"],),
            ).fetchone()
            leases = db.execute(
                "SELECT resource_id,scope_id,owner_id,fencing_token,state,heartbeat_ns,"
                "lease_until_ns,drained_at_ns FROM jeeves_idle_maintenance_lease"
                + scope_clause + " ORDER BY heartbeat_ns DESC LIMIT ?", (*scope_params, limit),
            ).fetchall()
            blocked = db.execute(
                "SELECT COUNT(*) FROM jeeves_idle_maintenance_task WHERE state='running' "
                "AND last_error LIKE 'recovery_blocked%'"
                + ("" if scope_id is None else " AND scope_id=?"), scope_params,
            ).fetchone()[0]
            clock = db.execute(
                "SELECT jump_count,last_jump_reason FROM jeeves_idle_maintenance_clock WHERE host_id=?",
                (self._identity["host_id"],),
            ).fetchone()
            host_foreground, host_owners = db.execute(
                "SELECT COALESCE(SUM(foreground_requests),0),COUNT(*) "
                "FROM jeeves_idle_maintenance_owner WHERE host_id=? AND state!='drained'",
                (self._identity["host_id"],),
            ).fetchone()
            chunks = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(result_json IS NULL),0),"
                "COALESCE(SUM(ack_state='unverified' AND result_json IS NOT NULL),0),"
                "COALESCE(SUM(ack_state='pending'),0),COALESCE(SUM(ack_failures),0),"
                "MIN(CASE WHEN ack_state='pending' THEN next_ack_ns END) "
                "FROM jeeves_idle_maintenance_chunk" + scope_clause, scope_params,
            ).fetchone()
            shared_chunks = db.execute("SELECT COUNT(*) FROM jeeves_idle_maintenance_chunk").fetchone()[0]
            ack_error = db.execute(
                "SELECT last_ack_error FROM jeeves_idle_maintenance_chunk WHERE last_ack_error IS NOT NULL"
                + ("" if scope_id is None else " AND scope_id=?")
                + " ORDER BY next_ack_ns DESC LIMIT 1", scope_params,
            ).fetchone()
            recovery_checked = db.execute(
                "SELECT MAX(recovery_checked_ns) FROM jeeves_idle_maintenance_task" + scope_clause,
                scope_params,
            ).fetchone()[0]
            tasks = [dict(zip(keys, row)) for row in rows]
            if scope_id is not None:
                shared_queue = db.execute(
                    "SELECT COUNT(*) FROM jeeves_idle_maintenance_task "
                    "WHERE state IN ('ready','retry_wait','running')",
                ).fetchone()[0]
                for task in tasks:
                    try:
                        handler = self._handlers.get(IdleWorkKind(task["kind"]))
                    except ValueError:
                        handler = None
                    reason = None
                    if task["state"] != "failed":
                        reason = "not_failed"
                    elif task["attempts"] >= 1_000_000:
                        reason = "attempt_limit"
                    elif handler is None:
                        reason = "handler_unavailable"
                    elif handler.version != task["handler_version"]:
                        reason = "handler_changed"
                    elif db.execute(
                        "SELECT 1 FROM jeeves_idle_maintenance_lease WHERE task_id=? AND state='held'",
                        (task["task_id"],),
                    ).fetchone() is not None:
                        reason = "custody_held"
                    elif task["attempts"] > 0 and task["drained_at_ns"] is None:
                        reason = "drain_unproven"
                    elif (shared_queue >= policy["maximum_queue"]
                          or queued >= min(policy["maximum_scope_queue"], policy["maximum_queue"])):
                        reason = "queue_full"
                    task["retryable"] = reason is None
                    task["retry_reason"] = reason
        result = {"schema": "jeeves.studio_maintenance.v1", "policy": policy,
                  "status": status, "queued_tasks": queued,
                  "recent_tasks": tasks,
                  "circuits": [dict(zip(("scope_id", "kind", "failures", "open_until_ns", "last_error"), row))
                               for row in circuits],
                  "execution_authority": "host-local-derived-only"}
        for task in result["recent_tasks"]:
            task["recovery_reason"] = (task["last_error"] if task["last_error"] is not None
                                       and task["last_error"].startswith("recovery_blocked") else None)
        result["ownership"] = None if owner is None else dict(zip(
            ("owner_id", "host_id", "state", "heartbeat_ns", "foreground_requests", "physical_tasks"), owner,
        ))
        result["leases"] = [dict(zip(
            ("resource_id", "scope_id", "owner_id", "fencing_token", "state", "heartbeat_ns",
             "lease_until_ns", "drained_at_ns"), row,
        )) for row in leases]
        result["recovery"] = {
            "blocked_tasks": blocked,
            "clock_jump_count": None if clock is None else clock[0],
            "last_clock_jump_reason": None if clock is None else clock[1],
            "last_checked_ns": recovery_checked,
        }
        result["chunk_results"] = {
            "retained": chunks[0], "reserved": chunks[1], "reusable_unverified": chunks[2],
            "shared_retained": shared_chunks, "maximum": policy["maximum_chunk_results"],
            "backpressure": shared_chunks >= policy["maximum_chunk_results"],
        }
        result["acknowledgements"] = {
            "pending": chunks[3], "failed_attempts": chunks[4], "next_retry_ns": chunks[5],
            "last_error": None if ack_error is None else ack_error[0],
            "callback_available": self._after_verified_chunk is not None,
        }
        result["quiescence"] = {
            "host_foreground_requests": host_foreground,
            "registered_host_owners": host_owners,
            "observation": "persisted_host_owner_heartbeats",
        }
        result["journal_capacity"] = {
            key: head[key] for key in ("event_count", "maximum_history_events", "remaining_events")
        }
        if scope_id is None:
            result["effect_history"] = head
        return result

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closing = True
            self._foreground_generation += 1
        # Lifespan owner must drain its tick task before closing repositories.
        # A cooperative callback will stop at its next checkpoint.
        with self._tick_lock:
            with self._state_lock:
                if self._closed:
                    return
            failures: list[BaseException] = []
            try:
                with self._executor._lock:
                    db = self._executor._db
                    try:
                        db.execute("BEGIN IMMEDIATE")
                        now = self._logical_now_locked(time_ns(), self._policy)
                        db.execute(
                            "UPDATE jeeves_idle_maintenance_owner SET state='drained',heartbeat_ns=?,"
                            "foreground_requests=0,physical_tasks=0 WHERE owner_id=?",
                            (now, self._identity["owner_id"]),
                        )
                        db.execute("COMMIT")
                    except BaseException as exc:
                        failures.append(exc)
                        try:
                            if db.in_transaction:
                                db.execute("ROLLBACK")
                        except BaseException as rollback_error:
                            failures.append(rollback_error)
            finally:
                # Losing durable drain proof must not leak the connection.
                # Future owners still require real process/host drain proof;
                # the local closed flag never fabricates a persisted receipt.
                try:
                    if self._owns_executor:
                        self._executor.close()
                except BaseException as close_error:
                    failures.append(close_error)
                finally:
                    with self._state_lock:
                        self._closed = True
            if len(failures) == 1:
                raise failures[0]
            if failures:
                raise BaseExceptionGroup("maintenance shutdown failed", failures)


def _validate_handlers(
    callbacks: Mapping[IdleWorkKind, MaintenanceHandler],
) -> dict[IdleWorkKind, MaintenanceHandler]:
    if (not isinstance(callbacks, Mapping) or not callbacks
            or len(callbacks) > len(LOCAL_MAINTENANCE_KINDS)
            or any(not isinstance(kind, IdleWorkKind)
                   or kind not in LOCAL_MAINTENANCE_KINDS
                   or not isinstance(handler, MaintenanceHandler)
                   for kind, handler in callbacks.items())):
        raise IdleRuntimeError("maintenance requires declared local retry-safe handlers")
    return dict(callbacks)


def create_studio_maintenance(
    *, store_path: str | Path,
    telemetry_probe: Callable[[], tuple[HostIdleTelemetry, int]],
    host_authorize: Callable[[IdleWorkAssignment, str, MaintenanceTask], bool],
    callbacks: Mapping[IdleWorkKind, MaintenanceHandler],
    idle_policy: IdleLearningPolicy | None = None,
    policy: StudioMaintenancePolicy | None = None,
    maximum_history_events: int = 200_000,
    owner_id: str | None = None,
    host_id: str | None = None,
    host_confirm_drained: Callable[[Mapping[str, Any]], bool | None] | None = None,
    after_verified_chunk: Callable[[MaintenanceTask, MaintenanceResult, HostIdleWorkReceipt], Any] | None = None,
) -> StudioMaintenanceController:
    """Build an engine-owned controller using the existing execution DB file.

    The host must validate exact tenant/scope/task provenance in authorize; a
    callback's presence cannot authorize a task. No credentials enter receipts.
    """
    handlers = _validate_handlers(callbacks)
    if not callable(host_authorize):
        raise IdleRuntimeError("maintenance requires exact host task authorization")

    def authorize(assignment: IdleWorkAssignment, intent: str, context: Any) -> bool:
        return (isinstance(context, _AttemptContext)
                and context.task.kind is assignment.kind
                and context.task.scope_id == assignment.scope_id
                and context.task.source_digest == assignment.source_digest
                and handlers.get(assignment.kind) is context.handler
                and host_authorize(assignment, intent, context.task) is True)

    def invoke(assignment: IdleWorkAssignment, context: Any,
               checkpoint: IdleWorkCheckpoint) -> HostIdleWorkReceipt:
        if not isinstance(context, _AttemptContext):
            raise IdleRuntimeError("maintenance worker lacks its exact host task")
        checkpoint()
        if context.controller is None:
            raise IdleRuntimeError("maintenance worker lacks its durable chunk owner")
        result = context.controller._prepare_chunk(context.task)
        if result is None:
            checkpoint()
            value = context.handler.callback(context.task, checkpoint)
            result = value if isinstance(value, MaintenanceResult) else MaintenanceResult(output=value)
            # Preserve actual callback completion before post-work pressure can
            # interrupt receipt admission. A retry reuses this exact chunk.
            context.controller._record_chunk(context.task, result)
        output_digest = _digest(dict(result.output))
        external_digest = context.controller._completion_digest(context.task, result)
        context.output = result
        # Poll after preserving the completed local result. If foreground
        # demand arrived, the executor records in-doubt custody and the queue
        # may repeat only this explicitly convergent local handler.
        checkpoint()
        context.receipt = HostIdleWorkReceipt(
            work_id=assignment.work_id, scope_id=assignment.scope_id,
            kind=assignment.kind, source_digest=assignment.source_digest,
            output_digest=output_digest, external_event_digest=external_digest,
            host_worker_id=context.task.owner_id, completed=True,
        )
        return context.receipt

    def verify(assignment: IdleWorkAssignment, receipt: HostIdleWorkReceipt,
               context: Any) -> bool:
        return (isinstance(context, _AttemptContext) and context.receipt is receipt
                and context.output is not None
                and receipt.output_digest == _digest(dict(context.output.output))
                and receipt.work_id == assignment.work_id)

    executor = JeevesIdleWorkExecutor(
        store_path=store_path, policy=idle_policy or IdleLearningPolicy(),
        host_authorize=authorize, handlers={kind: invoke for kind in handlers},
        verify_result=verify, telemetry_probe=telemetry_probe,
        maximum_history_events=maximum_history_events,
    )
    try:
        # Background lock contention must yield quickly to canonical execution
        # writes rather than monopolizing a SQLite busy wait for ten seconds.
        executor._db.execute("PRAGMA busy_timeout=100")
        return StudioMaintenanceController(
            executor=executor, callbacks=handlers, policy=policy, owns_executor=True,
            owner_id=owner_id, host_id=host_id, host_confirm_drained=host_confirm_drained,
            after_verified_chunk=after_verified_chunk,
        )
    except BaseException:
        executor.close()
        raise


__all__ = [
    "LOCAL_MAINTENANCE_KINDS", "StudioMaintenancePolicy", "MaintenanceTask",
    "MaintenanceResult", "MaintenanceHandler", "StudioMaintenanceController",
    "create_studio_maintenance",
]
