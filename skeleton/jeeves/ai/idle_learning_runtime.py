"""Durable host-executed idle-learning work with no automatic replay.

The scheduler proposes workloads using host telemetry. This adapter gives the
application one explicit worker invocation at a time and records the assignment
intent *before* executing an injected, independently authorized worker handler.

Model-supplied work proposals do not authorize crawler network access,
dataset writes, model training, weight promotion, or background CPU/GPU use.
Handlers remain owned by the application; each invocation requires live idle
telemetry, the host's exact scope authorization and external result proof.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any

from .idle_learning_scheduler import (
    HostIdleTelemetry, IdleLearningPolicy, IdleWorkAssignment,
    IdleWorkCandidate, IdleWorkKind, IdleWorkPlan, JeevesIdleLearningScheduler,
)


class IdleRuntimeError(ValueError):
    """Idle-work admission, durable lease or effect proof failed."""


class IdleExecutionState(str, Enum):
    IN_FLIGHT = "in_flight"
    VERIFIED = "verified"
    IN_DOUBT = "in_doubt"
    REJECTED = "rejected"


def _sha(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise IdleRuntimeError("idle evidence identity must be SHA-256")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise IdleRuntimeError("idle receipt cannot be canonically serialized") from exc
    if len(raw) > 64 * 1024:
        raise IdleRuntimeError("idle work metadata exceeds byte budget")
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class HostIdleWorkReceipt:
    work_id: str
    scope_id: str
    kind: IdleWorkKind
    source_digest: str
    output_digest: str
    external_event_digest: str
    host_worker_id: str
    completed: bool

    def __post_init__(self) -> None:
        for name in ("source_digest", "output_digest", "external_event_digest"):
            _sha(getattr(self, name))
        for name in ("work_id", "scope_id", "host_worker_id"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val or len(val) > 192:
                raise IdleRuntimeError("invalid host worker receipt identity")
        if not isinstance(self.kind, IdleWorkKind) or type(self.completed) is not bool:
            raise IdleRuntimeError("idle work receipt has invalid state")

    @property
    def digest(self) -> str:
        return _digest({
            "work_id": self.work_id, "scope_id": self.scope_id,
            "kind": self.kind.value, "source_digest": self.source_digest,
            "output_digest": self.output_digest,
            "external_event_digest": self.external_event_digest,
            "host_worker_id": self.host_worker_id,
            "completed": self.completed,
        })


_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jeeves_idle_effect (
    intent_digest TEXT PRIMARY KEY,
    work_id TEXT NOT NULL UNIQUE,
    scope_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    plan_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    receipt_digest TEXT,
    host_event_digest TEXT
);
"""


class JeevesIdleWorkExecutor:
    """One-shot task execution with durable idempotency and idle re-admission."""

    def __init__(
        self, *, store_path: str | Path,
        policy: IdleLearningPolicy,
        host_authorize: Callable[[IdleWorkAssignment, str, Any], bool],
        handlers: Mapping[IdleWorkKind, Callable[..., HostIdleWorkReceipt]],
        verify_result: Callable[[IdleWorkAssignment, HostIdleWorkReceipt, Any], bool],
    ) -> None:
        self.path = Path(store_path)
        if not self.path.is_absolute():
            raise IdleRuntimeError("idle-effect database requires host absolute path")
        if not isinstance(policy, IdleLearningPolicy):
            raise IdleRuntimeError("typed idle admission policy required")
        if not callable(host_authorize) or not callable(verify_result):
            raise IdleRuntimeError("independent idle work authorization and verifier required")
        if (not isinstance(handlers, Mapping) or not handlers
                or len(handlers) > len(IdleWorkKind)
                or any(not isinstance(key, IdleWorkKind) or not callable(callback)
                       for key, callback in handlers.items())):
            raise IdleRuntimeError("idle work handlers must be explicit typed host functions")
        self.policy = policy
        self._authorize = host_authorize
        self._handlers = dict(handlers)
        self._verify = verify_result
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), timeout=10, isolation_level=None, check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
        except BaseException:
            self._db.close()
            raise

    @staticmethod
    def _intent(plan: IdleWorkPlan, assignment: IdleWorkAssignment) -> str:
        return _digest({
            "schema": "jeeves.idle_work_intent.v1",
            "plan_digest": plan.digest,
            "work_id": assignment.work_id,
            "scope_id": assignment.scope_id,
            "kind": assignment.kind.value,
            "source_digest": assignment.source_digest,
            "cost_units": assignment.cost_units,
        })

    def _admit(
        self, plan: IdleWorkPlan, assignment: IdleWorkAssignment,
        candidate: IdleWorkCandidate, telemetry: HostIdleTelemetry,
        host_now_ns: int,
    ) -> None:
        if not all((
            isinstance(plan, IdleWorkPlan),
            isinstance(assignment, IdleWorkAssignment),
            isinstance(candidate, IdleWorkCandidate),
            isinstance(telemetry, HostIdleTelemetry),
        )):
            raise IdleRuntimeError("idle dispatch requires typed scheduling evidence")
        if (plan.plan_reason != "admitted_idle"
                or plan.required_host_reauthorization is not True
                or plan.observed_at_ns != telemetry.observed_at_ns
                or plan.telemetry_digest != telemetry.host_observation_digest
                or assignment not in plan.assignments):
            raise IdleRuntimeError("idle plan is not bound to current telemetry/assignment")
        if (assignment.work_id != candidate.work_id
                or assignment.scope_id != candidate.scope_id
                or assignment.kind is not candidate.kind
                or assignment.source_digest != candidate.source_digest
                or assignment.cost_units != candidate.cost_units):
            raise IdleRuntimeError("idle work candidate diverged after planning")
        if type(host_now_ns) is not int or host_now_ns < 0:
            raise IdleRuntimeError("host idle time invalid")
        if telemetry.pending_interactive_requests or telemetry.power_saving:
            raise IdleRuntimeError("idle work blocked by interactive or power policy")
        # Re-run the same admission logic with the chosen candidate and
        # current host-observed clock. No self-reported pressure is trusted.
        probe = JeevesIdleLearningScheduler(policy=self.policy).propose(
            (candidate,), telemetry, host_now_ns=host_now_ns,
        )
        if not probe.assignments or probe.assignments[0].work_id != assignment.work_id:
            raise IdleRuntimeError("host machine no longer admits idle work")

    def invoke_one(
        self, *, plan: IdleWorkPlan,
        assignment: IdleWorkAssignment, candidate: IdleWorkCandidate,
        telemetry: HostIdleTelemetry, host_now_ns: int,
        context: Any,
    ) -> tuple[IdleExecutionState, str]:
        with self._lock:
            self._admit(plan, assignment, candidate, telemetry, host_now_ns)
            handler = self._handlers.get(assignment.kind)
            if handler is None:
                raise IdleRuntimeError("host has no handler for this idle work kind")
            intent = self._intent(plan, assignment)
            if self._authorize(assignment, intent, context) is not True:
                raise IdleRuntimeError("host did not authorize exact idle work")
            try:
                self._db.execute("BEGIN IMMEDIATE")
                if self._db.execute(
                    "SELECT 1 FROM jeeves_idle_effect "
                    "WHERE intent_digest=? OR work_id=?",
                    (intent, assignment.work_id),
                ).fetchone():
                    raise IdleRuntimeError("idle work was already claimed or attempted")
                self._db.execute(
                    "INSERT INTO jeeves_idle_effect VALUES (?,?,?,?,?,?,?,?)",
                    (intent, assignment.work_id, assignment.scope_id,
                     assignment.source_digest, plan.digest,
                     IdleExecutionState.IN_FLIGHT.value, None, None),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            # Never wrap external effects in a retry loop. Any process crash
            # leaves the durable row in-flight and prevents blind duplicate work.
            result = handler(assignment, context)
            if not isinstance(result, HostIdleWorkReceipt):
                raise IdleRuntimeError("host idle handler returned untyped receipt")
            if (result.work_id != assignment.work_id
                    or result.scope_id != assignment.scope_id
                    or result.kind is not assignment.kind
                    or result.source_digest != assignment.source_digest
                    or not result.completed
                    or self._verify(assignment, result, context) is not True):
                state = IdleExecutionState.IN_DOUBT
            else:
                state = IdleExecutionState.VERIFIED
            self._db.execute(
                "UPDATE jeeves_idle_effect SET state=?,receipt_digest=?,"
                "host_event_digest=? WHERE intent_digest=? AND state=?",
                (state.value, result.digest, result.external_event_digest,
                 intent, IdleExecutionState.IN_FLIGHT.value),
            )
            return state, intent

    def pending(self, *, limit: int = 100) -> tuple[dict[str, str], ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise IdleRuntimeError("invalid pending idle work page size")
        with self._lock:
            rows = self._db.execute(
                "SELECT intent_digest,work_id,scope_id,source_digest,state "
                "FROM jeeves_idle_effect WHERE state IN (?,?) "
                "ORDER BY work_id LIMIT ?",
                (IdleExecutionState.IN_FLIGHT.value,
                 IdleExecutionState.IN_DOUBT.value, limit),
            )
            return tuple({
                "intent_digest": intent, "work_id": work,
                "scope_id": scope, "source_digest": source,
                "state": state,
            } for intent, work, scope, source, state in rows)

    def reconcile(
        self, intent_digest: str, *,
        external_event_digest: str,
        verify_external: Callable[[str, str], bool],
        confirmed_completed: bool,
    ) -> IdleExecutionState:
        """Host-only reconciliation; never calls the original worker again."""
        _sha(intent_digest)
        _sha(external_event_digest)
        if type(confirmed_completed) is not bool or not callable(verify_external):
            raise IdleRuntimeError("independent recovery proof required")
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT state FROM jeeves_idle_effect WHERE intent_digest=?",
                    (intent_digest,),
                ).fetchone()
                if row is None or row[0] not in (
                    IdleExecutionState.IN_FLIGHT.value,
                    IdleExecutionState.IN_DOUBT.value,
                ):
                    raise IdleRuntimeError("no unresolved host idle effect")
                if verify_external(intent_digest, external_event_digest) is not True:
                    raise IdleRuntimeError("external idle effect was not verified")
                state = (IdleExecutionState.VERIFIED if confirmed_completed
                         else IdleExecutionState.REJECTED)
                self._db.execute(
                    "UPDATE jeeves_idle_effect SET state=?,host_event_digest=? "
                    "WHERE intent_digest=?",
                    (state.value, external_event_digest, intent_digest),
                )
                self._db.execute("COMMIT")
                return state
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "JeevesIdleWorkExecutor":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "IdleRuntimeError", "IdleExecutionState",
    "HostIdleWorkReceipt", "JeevesIdleWorkExecutor",
]
