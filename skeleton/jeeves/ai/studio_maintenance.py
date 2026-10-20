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
from pathlib import Path
from threading import Lock, RLock
from time import monotonic_ns
from types import MappingProxyType
from typing import Any

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
_TASK_COLUMNS = (
    "task_id,scope_id,kind,source_digest,payload_digest,payload_json,priority,"
    "state,attempts,failures,next_run_ns,created_at_ns,updated_at_ns,"
    "lease_until_ns,last_error,last_intent,output_digest"
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
"""


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
    ) -> None:
        if not isinstance(executor, JeevesIdleWorkExecutor):
            raise IdleRuntimeError("maintenance requires the existing idle executor")
        self._handlers = _validate_handlers(callbacks)
        self._executor = executor
        self._policy = policy or StudioMaintenancePolicy()
        if not isinstance(self._policy, StudioMaintenancePolicy):
            raise IdleRuntimeError("maintenance requires typed policy")
        self._owns_executor = owns_executor
        self._state_lock = RLock()
        self._tick_lock = Lock()
        self._foreground_requests = 0
        self._foreground_generation = 0
        self._closed = False
        self._closing = False
        self._active_tasks = 0
        self._last_run_ns: int | None = None
        self._last_reason = "disabled" if not self._policy.enabled else "idle"
        with self._executor._lock:
            self._executor._db.executescript(_QUEUE_SCHEMA)

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
            self._last_reason = "idle" if policy.enabled else "disabled"
        return self.snapshot()

    def foreground_started(self) -> None:
        """Call before queueing foreground work, including resumed executions."""
        with self._state_lock:
            self._foreground_requests += 1
            self._foreground_generation += 1
            self._last_reason = "foreground_preemption"

    def foreground_finished(self) -> None:
        with self._state_lock:
            self._foreground_requests = max(0, self._foreground_requests - 1)

    def _preempted(self, generation: int) -> bool:
        with self._state_lock:
            return (self._closing or self._closed or not self._policy.enabled
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
        _, now_ns = self._now()
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
                db.execute(
                    "INSERT INTO jeeves_idle_maintenance_task VALUES "
                    "(?,?,?,?,?,?,?,'ready',0,0,?,?,?,0,NULL,NULL,NULL)",
                    (task_id, scope_id, kind.value, source_digest, payload_digest,
                     raw, priority, now_ns, now_ns, now_ns),
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
                # Expired leases only requeue these explicitly retry-safe local
                # handlers. General external idle effects are never replayed.
                expired = db.execute(
                    "SELECT task_id FROM jeeves_idle_maintenance_task "
                    "WHERE state='running' AND lease_until_ns<=? LIMIT ?",
                    (now_ns, min(32, policy.maximum_queue)),
                ).fetchall()
                for (task_id,) in expired:
                    db.execute(
                        "UPDATE jeeves_idle_maintenance_task SET state='retry_wait',"
                        "next_run_ns=?,updated_at_ns=?,lease_until_ns=0,"
                        "last_error='interrupted_local_chunk' WHERE task_id=?",
                        (now_ns + policy.preemption_backoff_ms * 1_000_000, now_ns, task_id),
                    )
                    self._event(task_id, "local_chunk_recovered", now_ns,
                                {"authority": "retry-safe-local-handler-only"})
                row = db.execute(
                    f"SELECT {_TASK_COLUMNS} FROM jeeves_idle_maintenance_task t "
                    f"WHERE state IN ('ready','retry_wait') AND next_run_ns<=? "
                    f"AND kind IN ({placeholders}) AND NOT EXISTS "
                    "(SELECT 1 FROM jeeves_idle_maintenance_circuit c "
                    "WHERE c.scope_id=t.scope_id AND c.kind=t.kind AND c.open_until_ns>?) "
                    "ORDER BY priority DESC,updated_at_ns,created_at_ns,task_id LIMIT 1",
                    (now_ns, *allowed, now_ns),
                ).fetchone()
                if row is None:
                    db.execute("COMMIT")
                    return None
                item = dict(zip(_TASK_COLUMNS.split(","), row))
                task = self._task_from_row(item, attempt=item["attempts"] + 1)
                lease_ns = (policy.maximum_chunk_wall_ms
                            + policy.interrupted_lease_grace_ms) * 1_000_000
                db.execute(
                    "UPDATE jeeves_idle_maintenance_task SET state='running',attempts=?,"
                    "updated_at_ns=?,lease_until_ns=? WHERE task_id=?",
                    (task.attempt, now_ns, now_ns + lease_ns, task.task_id),
                )
                self._event(task.task_id, "chunk_claimed", now_ns,
                            {"attempt": task.attempt, "lease_until_ns": now_ns + lease_ns})
                db.execute("COMMIT")
                return task
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
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise IdleRuntimeError("invalid persisted maintenance task") from exc
        return MaintenanceTask(
            task_id=item["task_id"], scope_id=item["scope_id"], kind=kind,
            source_digest=item["source_digest"], payload=MappingProxyType(payload),
            attempt=attempt, priority=item["priority"], created_at_ns=item["created_at_ns"],
        )

    def _finish(
        self, task: MaintenanceTask, *, now_ns: int, policy: StudioMaintenancePolicy,
        state: str, reason: str | None, intent: str | None = None,
        result: MaintenanceResult | None = None,
    ) -> None:
        with self._executor._lock:
            db = self._executor._db
            try:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT attempts,failures FROM jeeves_idle_maintenance_task "
                    "WHERE task_id=? AND state='running'", (task.task_id,),
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
                    failures = 0
                    db.execute(
                        "DELETE FROM jeeves_idle_maintenance_circuit WHERE scope_id=? AND kind=?",
                        (task.scope_id, task.kind.value),
                    )
                    if result is not None and not result.complete:
                        state = "ready"
                        if result.continuation is not None:
                            # Keep initial payload_digest for exact enqueue
                            # idempotency while advancing a host-owned cursor.
                            db.execute(
                                "UPDATE jeeves_idle_maintenance_task SET payload_json=? WHERE task_id=?",
                                (_canonical(dict(result.continuation)), task.task_id),
                            )
                db.execute(
                    "UPDATE jeeves_idle_maintenance_task SET state=?,failures=?,next_run_ns=?,"
                    "updated_at_ns=?,lease_until_ns=0,last_error=?,last_intent=?,output_digest=? "
                    "WHERE task_id=? AND attempts=?",
                    (state, failures, next_run_ns, now_ns, reason, intent, output_digest,
                     task.task_id, task.attempt),
                )
                self._event(task.task_id, "chunk_" + state, now_ns,
                            {"attempt": task.attempt, "state": state, "reason": reason,
                             "intent_digest": intent, "output_digest": output_digest,
                             "next_run_ns": next_run_ns, "failures": failures})
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
            with self._state_lock:
                policy = self._policy
                generation = self._foreground_generation
            if self._preempted(generation):
                reason = "disabled" if not policy.enabled else "foreground_preemption"
                with self._state_lock:
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
                        self._last_reason = "idle"
                    break
                with self._state_lock:
                    self._active_tasks = 1
                    self._last_run_ns = now_ns
                    self._last_reason = "running"
                context = _AttemptContext(task, self._handlers[task.kind])
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
                        stop_requested=lambda: self._preempted(generation),
                    )
                    if state is not IdleExecutionState.VERIFIED:
                        raise IdleWorkPreempted("chunk_idle_compliance_unconfirmed")
                    self._finish(task, now_ns=self._completion_time(now_ns), policy=policy,
                                 state="completed", reason=None, intent=intent,
                                 result=context.output)
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
            with self._state_lock:
                if self._last_reason == "running":
                    self._last_reason = "idle"
                reason = self._last_reason
            return {"state": reason, "processed": processed}
        finally:
            self._tick_lock.release()

    def _completion_time(self, prior_ns: int) -> int:
        try:
            _, now_ns = self._now()
            return max(prior_ns, now_ns)
        except Exception:
            # Receipt custody still commits if host telemetry becomes
            # unavailable after the chunk. No further work will be admitted.
            return prior_ns

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
                "SELECT task_id,scope_id,kind,state,priority,attempts,failures,"
                "next_run_ns,updated_at_ns,last_error,output_digest "
                "FROM jeeves_idle_maintenance_task" + scope_clause
                + " ORDER BY updated_at_ns DESC,task_id LIMIT ?",
                (*scope_params, limit),
            ).fetchall()
            keys = ("task_id", "scope_id", "kind", "state", "priority", "attempts", "failures",
                    "next_run_ns", "updated_at_ns", "last_error", "output_digest")
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
        result = {"schema": "jeeves.studio_maintenance.v1", "policy": policy,
                  "status": status, "queued_tasks": queued,
                  "recent_tasks": [dict(zip(keys, row)) for row in rows],
                  "circuits": [dict(zip(("scope_id", "kind", "failures", "open_until_ns", "last_error"), row))
                               for row in circuits],
                  "execution_authority": "host-local-derived-only"}
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
            if self._owns_executor:
                self._executor.close()
            with self._state_lock:
                self._closed = True


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
        value = context.handler.callback(context.task, checkpoint)
        result = value if isinstance(value, MaintenanceResult) else MaintenanceResult(output=value)
        output_digest = _digest(dict(result.output))
        external_digest = _digest({
            "schema": "jeeves.local_maintenance_result.v1",
            "task_id": context.task.task_id,
            "attempt": context.task.attempt,
            "kind": assignment.kind.value,
            "source_digest": assignment.source_digest,
            "handler_version": context.handler.version,
            "output_digest": output_digest,
            "complete": result.complete,
            "continuation_digest": (None if result.continuation is None
                                    else _digest(dict(result.continuation))),
        })
        context.output = result
        # Poll after preserving the completed local result. If foreground
        # demand arrived, the executor records in-doubt custody and the queue
        # may repeat only this explicitly convergent local handler.
        checkpoint()
        context.receipt = HostIdleWorkReceipt(
            work_id=assignment.work_id, scope_id=assignment.scope_id,
            kind=assignment.kind, source_digest=assignment.source_digest,
            output_digest=output_digest, external_event_digest=external_digest,
            host_worker_id="studio-local-maintenance", completed=True,
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
        )
    except BaseException:
        executor.close()
        raise


__all__ = [
    "LOCAL_MAINTENANCE_KINDS", "StudioMaintenancePolicy", "MaintenanceTask",
    "MaintenanceResult", "MaintenanceHandler", "StudioMaintenanceController",
    "create_studio_maintenance",
]
