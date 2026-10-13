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


class IdleWorkPreempted(IdleRuntimeError):
    """Trusted host telemetry no longer permits background work."""


class IdleWorkCheckpoint:
    """Cooperative worker preemption: call before each bounded source operation.

    Host worker handlers MUST use this checkpoint between external operations,
    batch items and expensive phases. The runner additionally samples before
    and after invoking a handler, but cannot preempt a noncooperative blocking
    handler already inside external code.
    """

    def __init__(
        self, *, policy: IdleLearningPolicy, candidate: IdleWorkCandidate,
        telemetry_probe: Callable[[], tuple[HostIdleTelemetry, int]],
    ) -> None:
        if not callable(telemetry_probe):
            raise IdleRuntimeError("host idle telemetry probe required")
        self._policy = policy
        self._candidate = candidate
        self._probe = telemetry_probe
        self.poll_count = 0

    def permitted(self) -> bool:
        observed = self._probe()
        if (not isinstance(observed, tuple) or len(observed) != 2
                or not isinstance(observed[0], HostIdleTelemetry)
                or type(observed[1]) is not int):
            raise IdleWorkPreempted("host telemetry probe returned invalid observation")
        telemetry, now_ns = observed
        self.poll_count += 1
        if (now_ns < telemetry.observed_at_ns
                or now_ns - telemetry.observed_at_ns > self._policy.maximum_telemetry_age_ns):
            return False
        if telemetry.pending_interactive_requests or telemetry.power_saving:
            return False
        if telemetry.quiet_ns < self._policy.minimum_idle_ns:
            return False
        if telemetry.serving_pressure_ppm >= self._policy.maximum_serving_pressure_ppm:
            return False
        if (telemetry.cpu_free_ppm < self._policy.minimum_cpu_free_ppm
                or telemetry.memory_free_ppm < self._policy.minimum_memory_free_ppm):
            return False
        if self._candidate.requires_network and not telemetry.online:
            return False
        if (self._candidate.requires_accelerator
                and telemetry.gpu_free_ppm < self._policy.minimum_gpu_free_ppm):
            return False
        # Current job counts as active during cooperative work, so do not
        # reject it solely because total worker concurrency is saturated.
        return True

    def __call__(self) -> None:
        if not self.permitted():
            raise IdleWorkPreempted("interactive demand or resource pressure preempted idle work")


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
CREATE TABLE IF NOT EXISTS jeeves_idle_event (
    sequence INTEGER PRIMARY KEY,
    prior_digest TEXT NOT NULL,
    event_digest TEXT NOT NULL UNIQUE,
    event_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jeeves_idle_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    head_digest TEXT NOT NULL,
    event_count INTEGER NOT NULL
);
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
        telemetry_probe: Callable[[], tuple[HostIdleTelemetry, int]],
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
        if not callable(telemetry_probe):
            raise IdleRuntimeError("host polling probe required for cooperative preemption")
        self._telemetry_probe = telemetry_probe
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), timeout=10, isolation_level=None, check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
            self._bootstrap_history()
        except BaseException:
            self._db.close()
            raise

    GENESIS = "0" * 64

    def _bootstrap_history(self) -> None:
        meta = self._db.execute(
            "SELECT head_digest,event_count FROM jeeves_idle_meta WHERE singleton=1"
        ).fetchone()
        if meta is None:
            if self._db.execute(
                "SELECT COUNT(*) FROM jeeves_idle_effect"
            ).fetchone()[0] or self._db.execute(
                "SELECT COUNT(*) FROM jeeves_idle_event"
            ).fetchone()[0]:
                raise IdleRuntimeError("idle effects exist without authoritative evidence history")
            self._db.execute(
                "INSERT INTO jeeves_idle_meta VALUES (1, ?, 0)", (self.GENESIS,),
            )
        self._verify_history()

    def _verify_history(self) -> None:
        prior = self.GENESIS
        count = 0
        materialized: dict[str, dict[str, Any]] = {}
        for sequence, stored_prior, digest, event_json in self._db.execute(
            "SELECT sequence,prior_digest,event_digest,event_json "
            "FROM jeeves_idle_event ORDER BY sequence"
        ):
            if count >= 200_000 or sequence != count or stored_prior != prior:
                raise IdleRuntimeError("idle event history is not sequential")
            if not isinstance(event_json, str) or len(event_json) > 65536:
                raise IdleRuntimeError("idle evidence entry exceeds byte budget")
            try:
                event = json.loads(event_json)
            except (TypeError, ValueError) as exc:
                raise IdleRuntimeError("idle evidence event is malformed") from exc
            if (not isinstance(event, dict)
                    or set(event) != {
                        "schema", "sequence", "prior_digest", "operation",
                        "at_ns", "effect",
                    }
                    or event["schema"] != "jeeves.idle_effect_event.v1"
                    or event["sequence"] != count
                    or event["prior_digest"] != prior
                    or _digest(event) != digest):
                raise IdleRuntimeError("idle effect journal digest mismatch")
            if type(event["at_ns"]) is not int or event["at_ns"] < 0:
                raise IdleRuntimeError("idle event timestamp invalid")
            effect = event["effect"]
            expected_keys = {
                "intent_digest", "work_id", "scope_id", "source_digest",
                "plan_digest", "state", "receipt_digest", "host_event_digest",
            }
            if not isinstance(effect, dict) or set(effect) != expected_keys:
                raise IdleRuntimeError("idle effect snapshot contract mismatch")
            intent = _sha(effect["intent_digest"])
            _sha(effect["source_digest"])
            _sha(effect["plan_digest"])
            for key in ("receipt_digest", "host_event_digest"):
                if effect[key] is not None:
                    _sha(effect[key])
            try:
                state = IdleExecutionState(effect["state"])
            except (ValueError, TypeError) as exc:
                raise IdleRuntimeError("invalid idle effect lifecycle state") from exc
            old = materialized.get(intent)
            if old is None:
                if state is not IdleExecutionState.IN_FLIGHT or event["operation"] != "claimed":
                    raise IdleRuntimeError("idle effect has no claimed genesis")
            else:
                if old["state"] == IdleExecutionState.IN_FLIGHT.value:
                    allowed = {
                        IdleExecutionState.VERIFIED, IdleExecutionState.IN_DOUBT,
                        IdleExecutionState.REJECTED,
                    }
                elif old["state"] == IdleExecutionState.IN_DOUBT.value:
                    allowed = {IdleExecutionState.VERIFIED, IdleExecutionState.REJECTED}
                else:
                    allowed = set()
                if state not in allowed:
                    raise IdleRuntimeError("idle effect history contains invalid transition")
                if any(old[key] != effect[key] for key in (
                    "intent_digest", "work_id", "scope_id", "source_digest", "plan_digest",
                )):
                    raise IdleRuntimeError("idle work identity changed after claiming")
            materialized[intent] = effect
            prior = digest
            count += 1
        meta = self._db.execute(
            "SELECT head_digest,event_count FROM jeeves_idle_meta WHERE singleton=1"
        ).fetchone()
        if meta != (prior, count):
            raise IdleRuntimeError("idle effect journal head is inconsistent")
        rows = self._db.execute(
            "SELECT intent_digest,work_id,scope_id,source_digest,"
            "plan_digest,state,receipt_digest,host_event_digest FROM jeeves_idle_effect"
        ).fetchall()
        if len(rows) != len(materialized):
            raise IdleRuntimeError("idle effects diverge from their evidence journal")
        keys = (
            "intent_digest", "work_id", "scope_id", "source_digest",
            "plan_digest", "state", "receipt_digest", "host_event_digest",
        )
        for row in rows:
            item = dict(zip(keys, row))
            if materialized.get(item["intent_digest"]) != item:
                raise IdleRuntimeError("idle materialized effect record was modified")

    def _append_event(self, intent: str, operation: str, *, at_ns: int) -> str:
        if type(at_ns) is not int or at_ns < 0:
            raise IdleRuntimeError("trusted host timestamp required for journal entry")
        current = self._db.execute(
            "SELECT head_digest,event_count FROM jeeves_idle_meta WHERE singleton=1"
        ).fetchone()
        if current is None or current[1] >= 200_000:
            raise IdleRuntimeError("idle journal metadata missing or capacity exhausted")
        head, number = current
        row = self._db.execute(
            "SELECT intent_digest,work_id,scope_id,source_digest,"
            "plan_digest,state,receipt_digest,host_event_digest "
            "FROM jeeves_idle_effect WHERE intent_digest=?", (intent,),
        ).fetchone()
        if row is None:
            raise IdleRuntimeError("idle journal cannot attest missing effect")
        keys = (
            "intent_digest", "work_id", "scope_id", "source_digest",
            "plan_digest", "state", "receipt_digest", "host_event_digest",
        )
        event = {
            "schema": "jeeves.idle_effect_event.v1",
            "sequence": number, "prior_digest": head,
            "operation": operation, "at_ns": at_ns,
            "effect": dict(zip(keys, row)),
        }
        digest = _digest(event)
        self._db.execute(
            "INSERT INTO jeeves_idle_event VALUES (?,?,?,?)",
            (number, head, digest, json.dumps(
                event, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            )),
        )
        self._db.execute(
            "UPDATE jeeves_idle_meta SET head_digest=?, event_count=? WHERE singleton=1",
            (digest, number + 1),
        )
        return digest

    def history_head(self, *, verify: bool = False) -> dict[str, Any]:
        """Expose constant-time custody metadata; optionally replay evidence."""
        if type(verify) is not bool:
            raise IdleRuntimeError("history verification selection must be boolean")
        with self._lock:
            if verify:
                self._verify_history()
            head, count = self._db.execute(
                "SELECT head_digest,event_count FROM jeeves_idle_meta WHERE singleton=1"
            ).fetchone()
            return {
                "schema": "jeeves.idle_effect_history.v1",
                "head_digest": head, "event_count": count,
                "authority": "host-worker-only",
            }

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
            checkpoint = IdleWorkCheckpoint(
                policy=self.policy, candidate=candidate,
                telemetry_probe=self._telemetry_probe,
            )
            checkpoint()
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
                self._append_event(intent, "claimed", at_ns=host_now_ns)
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            # Never replay external effects. The handler checks resource
            # pressure cooperatively, and interrupted/failed effects remain
            # in doubt until an independent host observes their outcome.
            try:
                result = handler(assignment, context, checkpoint)
            except BaseException:
                try:
                    self._db.execute("BEGIN IMMEDIATE")
                    updated = self._db.execute(
                        "UPDATE jeeves_idle_effect SET state=? "
                        "WHERE intent_digest=? AND state=?",
                        (IdleExecutionState.IN_DOUBT.value, intent,
                         IdleExecutionState.IN_FLIGHT.value),
                    )
                    if updated.rowcount == 1:
                        self._append_event(
                            intent, "worker_interrupted", at_ns=host_now_ns,
                        )
                    self._db.execute("COMMIT")
                except BaseException:
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    # The earlier durable IN_FLIGHT claim already blocks replay.
                raise
            # The handler has completed; renewed interactive demand prevents
            # confirmation of idle compliance, not custody of its receipt.
            completed_while_idle = checkpoint.permitted()
            if not isinstance(result, HostIdleWorkReceipt):
                raise IdleRuntimeError("host idle handler returned untyped receipt")
            if (result.work_id != assignment.work_id
                    or result.scope_id != assignment.scope_id
                    or result.kind is not assignment.kind
                    or result.source_digest != assignment.source_digest
                    or not result.completed or not completed_while_idle
                    or checkpoint.poll_count < 2
                    or self._verify(assignment, result, context) is not True):
                state = IdleExecutionState.IN_DOUBT
            else:
                state = IdleExecutionState.VERIFIED
            try:
                self._db.execute("BEGIN IMMEDIATE")
                updated = self._db.execute(
                    "UPDATE jeeves_idle_effect SET state=?,receipt_digest=?,"
                    "host_event_digest=? WHERE intent_digest=? AND state=?",
                    (state.value, result.digest, result.external_event_digest,
                     intent, IdleExecutionState.IN_FLIGHT.value),
                )
                if updated.rowcount != 1:
                    raise IdleRuntimeError("idle effect outcome was settled by another owner")
                self._append_event(intent, "worker_result", at_ns=host_now_ns)
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
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
        observed_at_ns: int,
    ) -> IdleExecutionState:
        """Host-only reconciliation; never calls the original worker again."""
        _sha(intent_digest)
        _sha(external_event_digest)
        if type(confirmed_completed) is not bool or not callable(verify_external):
            raise IdleRuntimeError("independent recovery proof required")
        if type(observed_at_ns) is not int or observed_at_ns < 0:
            raise IdleRuntimeError("host recovery observation timestamp required")
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
                updated = self._db.execute(
                    "UPDATE jeeves_idle_effect SET state=?,host_event_digest=? "
                    "WHERE intent_digest=? AND state IN (?,?)",
                    (state.value, external_event_digest, intent_digest,
                     IdleExecutionState.IN_FLIGHT.value,
                     IdleExecutionState.IN_DOUBT.value),
                )
                if updated.rowcount != 1:
                    raise IdleRuntimeError("idle effect reconciliation lost its lease")
                self._append_event(intent_digest, "external_reconciliation",
                                   at_ns=observed_at_ns)
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
    "IdleRuntimeError", "IdleWorkPreempted", "IdleWorkCheckpoint", "IdleExecutionState",
    "HostIdleWorkReceipt", "JeevesIdleWorkExecutor",
]
