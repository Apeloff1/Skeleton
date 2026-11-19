"""Durable cross-process pressure, queue, and concurrency coordination.

Process-local pressure is useful for scheduling, but it cannot prevent two API
workers from simultaneously admitting work against the same global capacity.
This SQLite reference ledger serializes those decisions with BEGIN IMMEDIATE
and gives every worker the same concurrency, queue, tenant-fairness,
lease-expiry, and overload-shedding view.
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4
import math
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path


class SharedPressureError(RuntimeError):
    """Base shared-pressure coordination failure."""


class SharedPressureExceeded(SharedPressureError):
    """Shared capacity rejected new work."""


class SharedPressureConflict(SharedPressureError):
    """An operation/task identity conflicts with an existing owner."""


def _id(value: str, field: str) -> str:
    value = str(value).strip()
    if not value:
        raise SharedPressureError(f"{field} is required")
    if len(value) > 256:
        raise SharedPressureError(f"{field} is too long")
    return value


def _positive(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SharedPressureError(f"{field} must be a positive integer")
    return value


def _priority(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000:
        raise SharedPressureError("priority must be an integer within [0, 1000]")
    return value


def _time(value: float | None, field: str) -> float:
    number = time.time() if value is None else float(value)
    if not math.isfinite(number) or number < 0:
        raise SharedPressureError(f"{field} must be finite and non-negative")
    return number


@dataclass(frozen=True, slots=True)
class SharedPressurePolicy:
    scope: str
    max_concurrency: int
    max_queue_depth: int
    max_tenant_concurrency: int
    max_tenant_queue_depth: int
    soft_shed_fraction: float = 0.8
    protect_priority_at_or_below: int = 10
    default_lease_seconds: float = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _id(self.scope, "scope"))
        for name in ("max_concurrency", "max_queue_depth", "max_tenant_concurrency", "max_tenant_queue_depth"):
            _positive(getattr(self, name), name)
        if self.max_tenant_concurrency > self.max_concurrency:
            raise SharedPressureError("max_tenant_concurrency cannot exceed max_concurrency")
        if self.max_tenant_queue_depth > self.max_queue_depth:
            raise SharedPressureError("max_tenant_queue_depth cannot exceed max_queue_depth")
        fraction = float(self.soft_shed_fraction)
        if not math.isfinite(fraction) or not 0 < fraction <= 1:
            raise SharedPressureError("soft_shed_fraction must be within (0, 1]")
        _priority(self.protect_priority_at_or_below)
        lease = float(self.default_lease_seconds)
        if not math.isfinite(lease) or lease <= 0:
            raise SharedPressureError("default_lease_seconds must be finite and positive")


@dataclass(frozen=True, slots=True)
class SharedPressureSnapshot:
    scope: str
    active: int
    queued: int
    max_concurrency: int
    max_queue_depth: int
    tenant_id: str | None = None
    tenant_active: int = 0
    tenant_queued: int = 0

    @property
    def concurrency_ratio(self) -> float:
        return self.active / max(1, self.max_concurrency)

    @property
    def queue_ratio(self) -> float:
        return self.queued / max(1, self.max_queue_depth)

    @property
    def pressure_ratio(self) -> float:
        return max(self.concurrency_ratio, self.queue_ratio)


@dataclass(frozen=True, slots=True)
class SharedPressureDecision:
    admitted: bool
    reason: str
    snapshot: SharedPressureSnapshot


@dataclass(frozen=True, slots=True)
class SharedPressureLease:
    lease_id: str
    scope: str
    operation_id: str
    tenant_id: str
    owner_id: str
    priority: int
    acquired_at: float
    expires_at: float


@dataclass(frozen=True, slots=True)
class SharedQueueTicket:
    ticket_id: str
    scope: str
    task_id: str
    tenant_id: str
    priority: int
    enqueued_at: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS shared_pressure_policy (
    scope TEXT PRIMARY KEY,
    max_concurrency INTEGER NOT NULL,
    max_queue_depth INTEGER NOT NULL,
    max_tenant_concurrency INTEGER NOT NULL,
    max_tenant_queue_depth INTEGER NOT NULL,
    soft_shed_fraction REAL NOT NULL,
    protect_priority_at_or_below INTEGER NOT NULL,
    default_lease_seconds REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shared_pressure_lease (
    lease_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    priority INTEGER NOT NULL,
    acquired_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    UNIQUE (scope, operation_id)
);
CREATE INDEX IF NOT EXISTS idx_pressure_lease_scope ON shared_pressure_lease (scope, expires_at);
CREATE INDEX IF NOT EXISTS idx_pressure_lease_tenant ON shared_pressure_lease (scope, tenant_id, expires_at);
CREATE TABLE IF NOT EXISTS shared_pressure_queue (
    ticket_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    task_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    priority INTEGER NOT NULL,
    enqueued_at REAL NOT NULL,
    UNIQUE (scope, task_id)
);
CREATE INDEX IF NOT EXISTS idx_pressure_queue_scope ON shared_pressure_queue (scope, priority, enqueued_at);
CREATE INDEX IF NOT EXISTS idx_pressure_queue_tenant ON shared_pressure_queue (scope, tenant_id);
CREATE TABLE IF NOT EXISTS shared_pressure_promotion_receipt (
    scope TEXT NOT NULL,
    request_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    identity_digest TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('ranked', 'group')),
    lease_ids_json TEXT NOT NULL,
    committed_at REAL NOT NULL,
    PRIMARY KEY (scope, request_id)
);
"""


def _lease_id(scope: str, operation: str, tenant: str, owner: str) -> str:
    # A new reservation must not reuse a previous attempt's release fence.
    # Live operation retries return the existing row before invoking this helper.
    return "prs-" + uuid4().hex


def _ticket_id(scope: str, task: str, tenant: str) -> str:
    # Retry of a currently queued task returns its persisted ticket. Requeue
    # after removal gets a different generation even if the clock is unchanged.
    return "prq-" + uuid4().hex


class SqliteSharedPressureLedger:
    """Restart-safe coordination for workers sharing one SQLite database."""

    def __init__(self, path: str | Path, *, timeout_seconds: float = 10.0) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise SharedPressureError("shared pressure requires a filesystem path")
        self.timeout_seconds = float(timeout_seconds)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise SharedPressureError("timeout_seconds must be finite and positive")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=self.timeout_seconds, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @staticmethod
    def _policy(row: sqlite3.Row) -> SharedPressurePolicy:
        return SharedPressurePolicy(
            scope=str(row["scope"]),
            max_concurrency=int(row["max_concurrency"]),
            max_queue_depth=int(row["max_queue_depth"]),
            max_tenant_concurrency=int(row["max_tenant_concurrency"]),
            max_tenant_queue_depth=int(row["max_tenant_queue_depth"]),
            soft_shed_fraction=float(row["soft_shed_fraction"]),
            protect_priority_at_or_below=int(row["protect_priority_at_or_below"]),
            default_lease_seconds=float(row["default_lease_seconds"]),
        )

    @staticmethod
    def _lease(row: sqlite3.Row) -> SharedPressureLease:
        return SharedPressureLease(str(row["lease_id"]), str(row["scope"]), str(row["operation_id"]), str(row["tenant_id"]), str(row["owner_id"]), int(row["priority"]), float(row["acquired_at"]), float(row["expires_at"]))

    @staticmethod
    def _ticket(row: sqlite3.Row) -> SharedQueueTicket:
        return SharedQueueTicket(str(row["ticket_id"]), str(row["scope"]), str(row["task_id"]), str(row["tenant_id"]), int(row["priority"]), float(row["enqueued_at"]))

    @staticmethod
    def _policy_row(conn: sqlite3.Connection, scope: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM shared_pressure_policy WHERE scope = ?", (scope,)).fetchone()
        if row is None:
            raise SharedPressureError("pressure scope is not configured")
        return row

    @staticmethod
    def _reap(conn: sqlite3.Connection, scope: str, now: float) -> int:
        return int(conn.execute("DELETE FROM shared_pressure_lease WHERE scope = ? AND expires_at <= ?", (scope, now)).rowcount)

    @classmethod
    def _snapshot(cls, conn: sqlite3.Connection, policy: SharedPressurePolicy, tenant: str | None) -> SharedPressureSnapshot:
        active = int(conn.execute("SELECT COUNT(*) FROM shared_pressure_lease WHERE scope = ?", (policy.scope,)).fetchone()[0])
        queued = int(conn.execute("SELECT COUNT(*) FROM shared_pressure_queue WHERE scope = ?", (policy.scope,)).fetchone()[0])
        tenant_active = tenant_queued = 0
        if tenant is not None:
            tenant_active = int(conn.execute("SELECT COUNT(*) FROM shared_pressure_lease WHERE scope = ? AND tenant_id = ?", (policy.scope, tenant)).fetchone()[0])
            tenant_queued = int(conn.execute("SELECT COUNT(*) FROM shared_pressure_queue WHERE scope = ? AND tenant_id = ?", (policy.scope, tenant)).fetchone()[0])
        return SharedPressureSnapshot(policy.scope, active, queued, policy.max_concurrency, policy.max_queue_depth, tenant, tenant_active, tenant_queued)

    @staticmethod
    def _decision(policy: SharedPressurePolicy, snap: SharedPressureSnapshot, priority: int, *, for_queue: bool) -> SharedPressureDecision:
        if for_queue:
            if snap.queued >= policy.max_queue_depth:
                return SharedPressureDecision(False, "shared_queue_saturated", snap)
            if snap.tenant_queued >= policy.max_tenant_queue_depth:
                return SharedPressureDecision(False, "tenant_queue_saturated", snap)
        else:
            if snap.active >= policy.max_concurrency:
                return SharedPressureDecision(False, "shared_concurrency_saturated", snap)
            if snap.tenant_active >= policy.max_tenant_concurrency:
                return SharedPressureDecision(False, "tenant_concurrency_saturated", snap)
        if priority > policy.protect_priority_at_or_below and snap.pressure_ratio >= policy.soft_shed_fraction:
            return SharedPressureDecision(False, "soft_pressure_shed", snap)
        return SharedPressureDecision(True, "within_shared_pressure", snap)

    @classmethod
    def _promotion_decision(cls, policy: SharedPressurePolicy, snap: SharedPressureSnapshot,
                            priority: int) -> SharedPressureDecision:
        # Queue pressure gates NEW admission, not drainage of already admitted
        # tickets. Otherwise a full queued backlog can permanently block itself.
        drain_snapshot = SharedPressureSnapshot(
            snap.scope, snap.active, 0, snap.max_concurrency, snap.max_queue_depth,
            snap.tenant_id, snap.tenant_active, snap.tenant_queued,
        )
        decision = cls._decision(policy, drain_snapshot, priority, for_queue=False)
        return SharedPressureDecision(decision.admitted, decision.reason, snap)

    @staticmethod
    def _promotion_identity(
        kind: str, scope: str, owner: str, tickets: tuple[SharedQueueTicket, ...],
        duration: float | None, aging_interval_ms: int | None,
    ) -> str:
        if duration is not None and (isinstance(duration, bool) or
                not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0):
            raise SharedPressureError("invalid requested lease duration")
        payload = {
            "version": 1, "kind": kind, "scope": scope, "owner": owner,
            "tickets": [asdict(t) for t in sorted(tickets, key=lambda t: t.ticket_id)],
            "duration": None if duration is None else float(duration),
            "aging_interval_ms": aging_interval_ms,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True, allow_nan=False).encode()).hexdigest()

    @classmethod
    def _read_promotion_receipt(
        cls, conn: sqlite3.Connection, scope: str, request_id: str, owner: str,
        kind: str, identity: str, now: float,
    ) -> tuple[SharedPressureLease, ...] | None:
        row = conn.execute(
            "SELECT * FROM shared_pressure_promotion_receipt WHERE scope = ? AND request_id = ?",
            (scope, request_id),
        ).fetchone()
        if row is None:
            # Keep terminal identities as tombstones: TTL deletion would
            # silently reopen a replay window. Bound the scope explicitly.
            count = conn.execute(
                "SELECT COUNT(*) FROM shared_pressure_promotion_receipt WHERE scope = ?", (scope,)
            ).fetchone()[0]
            if count >= 100_000:
                raise SharedPressureExceeded("promotion receipt retention exhausted")
            return None
        if row["owner_id"] != owner or row["kind"] != kind or row["identity_digest"] != identity:
            raise SharedPressureConflict("promotion request identity mismatch")
        raw = row["lease_ids_json"]
        if type(raw) is not str or len(raw) > 4096:
            raise SharedPressureConflict("promotion receipt corrupt")
        try:
            ids = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise SharedPressureConflict("promotion receipt corrupt") from exc
        if (type(ids) is not list or not 1 <= len(ids) <= 64 or
                any(type(x) is not str or not x or len(x) > 128 for x in ids) or
                len(set(ids)) != len(ids) or (kind == "ranked" and len(ids) != 1)):
            raise SharedPressureConflict("promotion receipt corrupt")
        leases = []
        for lease_id in ids:
            lease_row = conn.execute(
                "SELECT * FROM shared_pressure_lease WHERE lease_id = ?", (lease_id,),
            ).fetchone()
            if lease_row is None:
                raise SharedPressureConflict("committed promotion is no longer fully live")
            lease = cls._lease(lease_row)
            if lease.scope != scope or lease.owner_id != owner or lease.expires_at <= now:
                raise SharedPressureConflict("committed promotion is no longer fully live")
            leases.append(lease)
        return tuple(leases)

    @staticmethod
    def _record_promotion(
        conn: sqlite3.Connection, scope: str, request_id: str, owner: str,
        kind: str, identity: str, leases: tuple[SharedPressureLease, ...], now: float,
    ) -> None:
        conn.execute(
            "INSERT INTO shared_pressure_promotion_receipt "
            "(scope, request_id, owner_id, identity_digest, kind, lease_ids_json, committed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (scope, request_id, owner, identity, kind,
             json.dumps([lease.lease_id for lease in leases], separators=(",", ":")), now),
        )

    def configure(self, policy: SharedPressurePolicy, *, replace: bool = False) -> SharedPressurePolicy:
        if not isinstance(policy, SharedPressurePolicy):
            raise TypeError("policy must be SharedPressurePolicy")
        with self._write() as conn:
            existing = conn.execute("SELECT 1 FROM shared_pressure_policy WHERE scope = ?", (policy.scope,)).fetchone()
            if existing is not None and not replace:
                raise SharedPressureConflict("pressure scope already configured")
            snap = self._snapshot(conn, policy, None)
            if replace and (snap.active > policy.max_concurrency or snap.queued > policy.max_queue_depth):
                raise SharedPressureConflict("replacement policy is below current pressure")
            if replace:
                active_max = conn.execute(
                    "SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM shared_pressure_lease "
                    "WHERE scope = ? GROUP BY tenant_id)", (policy.scope,),
                ).fetchone()[0] or 0
                queue_max = conn.execute(
                    "SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM shared_pressure_queue "
                    "WHERE scope = ? GROUP BY tenant_id)", (policy.scope,),
                ).fetchone()[0] or 0
                if active_max > policy.max_tenant_concurrency or queue_max > policy.max_tenant_queue_depth:
                    raise SharedPressureConflict("replacement policy is below current tenant pressure")
            conn.execute("""
                INSERT OR REPLACE INTO shared_pressure_policy
                (scope, max_concurrency, max_queue_depth, max_tenant_concurrency,
                 max_tenant_queue_depth, soft_shed_fraction,
                 protect_priority_at_or_below, default_lease_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (policy.scope, policy.max_concurrency, policy.max_queue_depth, policy.max_tenant_concurrency, policy.max_tenant_queue_depth, policy.soft_shed_fraction, policy.protect_priority_at_or_below, policy.default_lease_seconds))
        return policy

    def snapshot(self, scope: str, *, tenant_id: str | None = None, now: float | None = None) -> SharedPressureSnapshot:
        scope = _id(scope, "scope")
        tenant = None if tenant_id is None else _id(tenant_id, "tenant_id")
        timestamp = _time(now, "now")
        with self._write() as conn:
            policy = self._policy(self._policy_row(conn, scope))
            self._reap(conn, scope, timestamp)
            return self._snapshot(conn, policy, tenant)

    def decide(self, scope: str, tenant_id: str, *, priority: int = 100, for_queue: bool = False, now: float | None = None) -> SharedPressureDecision:
        scope = _id(scope, "scope")
        tenant = _id(tenant_id, "tenant_id")
        priority = _priority(priority)
        timestamp = _time(now, "now")
        with self._write() as conn:
            policy = self._policy(self._policy_row(conn, scope))
            self._reap(conn, scope, timestamp)
            return self._decision(policy, self._snapshot(conn, policy, tenant), priority, for_queue=for_queue)

    def enqueue(self, scope: str, tenant_id: str, task_id: str, *, priority: int = 100, now: float | None = None) -> SharedQueueTicket:
        scope, tenant, task = _id(scope, "scope"), _id(tenant_id, "tenant_id"), _id(task_id, "task_id")
        priority, timestamp = _priority(priority), _time(now, "now")
        with self._write() as conn:
            policy = self._policy(self._policy_row(conn, scope))
            self._reap(conn, scope, timestamp)
            existing = conn.execute("SELECT * FROM shared_pressure_queue WHERE scope = ? AND task_id = ?", (scope, task)).fetchone()
            if existing is not None:
                ticket = self._ticket(existing)
                if ticket.tenant_id != tenant or ticket.priority != priority:
                    raise SharedPressureConflict("task already queued with different ownership")
                return ticket
            decision = self._decision(policy, self._snapshot(conn, policy, tenant), priority, for_queue=True)
            if not decision.admitted:
                raise SharedPressureExceeded(decision.reason)
            ticket = SharedQueueTicket(_ticket_id(scope, task, tenant), scope, task, tenant, priority, timestamp)
            conn.execute("INSERT INTO shared_pressure_queue (ticket_id, scope, task_id, tenant_id, priority, enqueued_at) VALUES (?, ?, ?, ?, ?, ?)", (ticket.ticket_id, ticket.scope, ticket.task_id, ticket.tenant_id, ticket.priority, ticket.enqueued_at))
            return ticket

    def acquire(self, scope: str, tenant_id: str, operation_id: str, owner_id: str, *, priority: int = 100, lease_seconds: float | None = None, now: float | None = None) -> SharedPressureLease:
        scope, tenant = _id(scope, "scope"), _id(tenant_id, "tenant_id")
        operation, owner = _id(operation_id, "operation_id"), _id(owner_id, "owner_id")
        priority, timestamp = _priority(priority), _time(now, "now")
        with self._write() as conn:
            policy = self._policy(self._policy_row(conn, scope))
            self._reap(conn, scope, timestamp)
            existing = conn.execute("SELECT * FROM shared_pressure_lease WHERE scope = ? AND operation_id = ?", (scope, operation)).fetchone()
            if existing is not None:
                lease = self._lease(existing)
                if lease.tenant_id != tenant or lease.owner_id != owner or lease.priority != priority:
                    raise SharedPressureConflict("operation already leased with different ownership")
                return lease
            decision = self._decision(policy, self._snapshot(conn, policy, tenant), priority, for_queue=False)
            if not decision.admitted:
                raise SharedPressureExceeded(decision.reason)
            duration = policy.default_lease_seconds if lease_seconds is None else float(lease_seconds)
            if not math.isfinite(duration) or duration <= 0:
                raise SharedPressureError("lease_seconds must be finite and positive")
            lease = SharedPressureLease(_lease_id(scope, operation, tenant, owner), scope, operation, tenant, owner, priority, timestamp, timestamp + duration)
            conn.execute("INSERT INTO shared_pressure_lease (lease_id, scope, operation_id, tenant_id, owner_id, priority, acquired_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (lease.lease_id, lease.scope, lease.operation_id, lease.tenant_id, lease.owner_id, lease.priority, lease.acquired_at, lease.expires_at))
            return lease

    def promote(self, ticket_id: str, owner_id: str, *, lease_seconds: float | None = None, now: float | None = None) -> SharedPressureLease:
        ticket_id, owner, timestamp = _id(ticket_id, "ticket_id"), _id(owner_id, "owner_id"), _time(now, "now")
        with self._write() as conn:
            row = conn.execute("SELECT * FROM shared_pressure_queue WHERE ticket_id = ?", (ticket_id,)).fetchone()
            if row is None:
                raise SharedPressureError("unknown queue ticket")
            ticket = self._ticket(row)
            policy = self._policy(self._policy_row(conn, ticket.scope))
            self._reap(conn, ticket.scope, timestamp)
            decision = self._promotion_decision(policy, self._snapshot(conn, policy, ticket.tenant_id), ticket.priority)
            if not decision.admitted:
                raise SharedPressureExceeded(decision.reason)
            duration = policy.default_lease_seconds if lease_seconds is None else float(lease_seconds)
            if not math.isfinite(duration) or duration <= 0:
                raise SharedPressureError("lease_seconds must be finite and positive")
            lease = SharedPressureLease(_lease_id(ticket.scope, ticket.task_id, ticket.tenant_id, owner), ticket.scope, ticket.task_id, ticket.tenant_id, owner, ticket.priority, timestamp, timestamp + duration)
            conn.execute("INSERT INTO shared_pressure_lease (lease_id, scope, operation_id, tenant_id, owner_id, priority, acquired_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (lease.lease_id, lease.scope, lease.operation_id, lease.tenant_id, lease.owner_id, lease.priority, lease.acquired_at, lease.expires_at))
            conn.execute("DELETE FROM shared_pressure_queue WHERE ticket_id = ?", (ticket_id,))
            return lease

    def promote_ranked(
        self,
        scope: str,
        owner_id: str,
        *,
        authorized_tickets: tuple[SharedQueueTicket, ...],
        now: float | None = None,
        lease_seconds: float | None = None,
        aging_interval_ms: int = 30_000,
        request_id: str | None = None,
    ) -> SharedPressureLease | None:
        """Select and promote one explicitly authorized ticket atomically.

        No implicit worker authority: the caller provides exact previously
        admitted ticket records for work that this worker is allowed to run.
        The ledger rechecks records, hard caps and soft pressure in one write
        transaction. Existing direct-promotion semantics remain unchanged.
        """
        from .dispatch_policy import DispatchCandidate, rank_candidates

        scope, owner = _id(scope, "scope"), _id(owner_id, "owner_id")
        timestamp = _time(now, "now")
        if type(authorized_tickets) is not tuple or len(authorized_tickets) > 4096:
            raise SharedPressureError("invalid authorized ticket set")
        if any(not isinstance(t, SharedQueueTicket) or t.scope != scope for t in authorized_tickets):
            raise SharedPressureConflict("authorized ticket scope mismatch")
        if len({t.ticket_id for t in authorized_tickets}) != len(authorized_tickets):
            raise SharedPressureConflict("duplicate authorized ticket")
        if type(aging_interval_ms) is not int or not 1 <= aging_interval_ms <= 10**15:
            raise SharedPressureError("invalid aging interval")
        receipt_id = None if request_id is None else _id(request_id, "request_id")
        identity = None if receipt_id is None else self._promotion_identity(
            "ranked", scope, owner, authorized_tickets, lease_seconds, aging_interval_ms,
        )
        with self._write() as conn:
            policy = self._policy(self._policy_row(conn, scope))
            self._reap(conn, scope, timestamp)
            if receipt_id is not None:
                replay = self._read_promotion_receipt(conn, scope, receipt_id, owner, "ranked", identity, timestamp)
                if replay is not None:
                    return replay[0]
            global_snap = self._snapshot(conn, policy, None)
            if global_snap.active >= policy.max_concurrency:
                return None
            counts: dict[str, int] = {}
            candidates: list[DispatchCandidate] = []
            tickets: dict[str, SharedQueueTicket] = {}
            for expected in authorized_tickets:
                if not isinstance(expected, SharedQueueTicket) or expected.scope != scope:
                    raise SharedPressureConflict("authorized ticket scope mismatch")
                if expected.ticket_id in tickets:
                    raise SharedPressureConflict("duplicate authorized ticket")
                tickets[expected.ticket_id] = expected
                row = conn.execute(
                    "SELECT * FROM shared_pressure_queue WHERE ticket_id = ?", (expected.ticket_id,)
                ).fetchone()
                if row is None:
                    continue
                if self._ticket(row) != expected:
                    raise SharedPressureConflict("authorized ticket changed")
                if expected.tenant_id not in counts:
                    counts[expected.tenant_id] = int(conn.execute(
                        "SELECT COUNT(*) FROM shared_pressure_lease WHERE scope = ? AND tenant_id = ?",
                        (scope, expected.tenant_id),
                    ).fetchone()[0])
                snap = SharedPressureSnapshot(
                    scope, global_snap.active, global_snap.queued,
                    policy.max_concurrency, policy.max_queue_depth,
                    expected.tenant_id, counts[expected.tenant_id],
                )
                if not self._promotion_decision(policy, snap, expected.priority).admitted:
                    continue
                if conn.execute(
                    "SELECT 1 FROM shared_pressure_lease WHERE scope = ? AND operation_id = ?",
                    (scope, expected.task_id),
                ).fetchone() is not None:
                    continue
                candidates.append(DispatchCandidate(
                    expected.ticket_id, expected.tenant_id, expected.priority,
                    int(expected.enqueued_at * 1000),
                ))
            ranking = rank_candidates(
                candidates, now_ms=int(timestamp * 1000), tenant_active=counts,
                aging_interval_ms=aging_interval_ms,
                protected_priority=policy.protect_priority_at_or_below,
            )
            if not ranking:
                return None
            lease = self._insert_ranked_lease(
                conn, policy, tickets[ranking[0].ticket_id], owner, timestamp, lease_seconds,
            )
            if receipt_id is not None:
                self._record_promotion(conn, scope, receipt_id, owner, "ranked", identity, (lease,), timestamp)
            return lease

    def promote_group(
        self,
        scope: str,
        owner_id: str,
        *,
        authorized_tickets: tuple[SharedQueueTicket, ...],
        now: float | None = None,
        lease_seconds: float | None = None,
        request_id: str | None = None,
    ) -> tuple[SharedPressureLease, ...]:
        """Atomically reserve every authorized member or roll back all members.

        This reserves logical slots in one existing pressure scope, not GPUs
        or physical nodes. The caller must separately hold physical resources.
        """
        scope, owner = _id(scope, "scope"), _id(owner_id, "owner_id")
        timestamp = _time(now, "now")
        if type(authorized_tickets) is not tuple or not 1 <= len(authorized_tickets) <= 64:
            raise SharedPressureError("invalid group size")
        if any(not isinstance(t, SharedQueueTicket) or t.scope != scope for t in authorized_tickets):
            raise SharedPressureConflict("authorized group scope mismatch")
        if len({t.ticket_id for t in authorized_tickets}) != len(authorized_tickets):
            raise SharedPressureConflict("duplicate authorized group ticket")
        receipt_id = None if request_id is None else _id(request_id, "request_id")
        identity = None if receipt_id is None else self._promotion_identity(
            "group", scope, owner, authorized_tickets, lease_seconds, None,
        )
        with self._write() as conn:
            policy = self._policy(self._policy_row(conn, scope))
            self._reap(conn, scope, timestamp)
            if receipt_id is not None:
                replay = self._read_promotion_receipt(conn, scope, receipt_id, owner, "group", identity, timestamp)
                if replay is not None:
                    return replay
            if self._snapshot(conn, policy, None).active + len(authorized_tickets) > policy.max_concurrency:
                raise SharedPressureExceeded("shared_concurrency_saturated")
            leases: list[SharedPressureLease] = []
            for expected in sorted(authorized_tickets, key=lambda t: (t.priority, t.ticket_id)):
                row = conn.execute(
                    "SELECT * FROM shared_pressure_queue WHERE ticket_id = ?", (expected.ticket_id,)
                ).fetchone()
                if row is None or self._ticket(row) != expected:
                    raise SharedPressureConflict("authorized group ticket unavailable")
                decision = self._promotion_decision(
                    policy, self._snapshot(conn, policy, expected.tenant_id),
                    expected.priority,
                )
                if not decision.admitted:
                    raise SharedPressureExceeded(decision.reason)
                leases.append(self._insert_ranked_lease(
                    conn, policy, expected, owner, timestamp, lease_seconds,
                ))
            result = tuple(leases)
            if receipt_id is not None:
                self._record_promotion(conn, scope, receipt_id, owner, "group", identity, result, timestamp)
            return result

    @staticmethod
    def _insert_ranked_lease(
        conn: sqlite3.Connection,
        policy: SharedPressurePolicy,
        ticket: SharedQueueTicket,
        owner: str,
        timestamp: float,
        lease_seconds: float | None,
    ) -> SharedPressureLease:
        duration = policy.default_lease_seconds if lease_seconds is None else float(lease_seconds)
        if not math.isfinite(duration) or duration <= 0 or not math.isfinite(timestamp + duration):
            raise SharedPressureError("lease_seconds must be finite and positive")
        # Every new reservation gets a distinct fence. Replay must use the
        # original committed receipt or a current exact operation lookup.
        lease = SharedPressureLease(
            "prs-" + uuid4().hex, ticket.scope, ticket.task_id,
            ticket.tenant_id, owner, ticket.priority, timestamp, timestamp + duration,
        )
        try:
            conn.execute(
                "INSERT INTO shared_pressure_lease "
                "(lease_id, scope, operation_id, tenant_id, owner_id, priority, acquired_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lease.lease_id, lease.scope, lease.operation_id, lease.tenant_id,
                 lease.owner_id, lease.priority, lease.acquired_at, lease.expires_at),
            )
        except sqlite3.IntegrityError as exc:
            raise SharedPressureConflict("operation already leased") from exc
        if conn.execute(
            "DELETE FROM shared_pressure_queue WHERE ticket_id = ?", (ticket.ticket_id,)
        ).rowcount != 1:
            raise SharedPressureConflict("queue ticket changed during promotion")
        return lease

    def lease_for_operation(
        self,
        scope: str,
        operation_id: str,
        *,
        now: float | None = None,
    ) -> SharedPressureLease | None:
        """Return one still-live operation lease after deterministic expiry reap."""

        clean_scope = _id(scope, "scope")
        operation = _id(operation_id, "operation_id")
        timestamp = _time(now, "now")
        with self._write() as conn:
            self._policy_row(conn, clean_scope)
            self._reap(conn, clean_scope, timestamp)
            row = conn.execute(
                """
                SELECT * FROM shared_pressure_lease
                WHERE scope = ? AND operation_id = ?
                """,
                (clean_scope, operation),
            ).fetchone()
            return None if row is None else self._lease(row)

    def renew(self, lease_id: str, owner_id: str, *, lease_seconds: float | None = None, now: float | None = None) -> SharedPressureLease:
        lease_id, owner, timestamp = _id(lease_id, "lease_id"), _id(owner_id, "owner_id"), _time(now, "now")
        with self._write() as conn:
            row = conn.execute("SELECT * FROM shared_pressure_lease WHERE lease_id = ?", (lease_id,)).fetchone()
            if row is None:
                raise SharedPressureError("unknown pressure lease")
            lease = self._lease(row)
            if lease.owner_id != owner:
                raise SharedPressureConflict("pressure lease owner mismatch")
            # Expiry is a hard fencing boundary. A stale worker must never be
            # able to resurrect authority after its durable lease elapsed,
            # even if no other reader has reaped the expired row yet.
            if timestamp >= lease.expires_at:
                raise SharedPressureConflict("pressure lease expired")
            policy = self._policy(self._policy_row(conn, lease.scope))
            duration = policy.default_lease_seconds if lease_seconds is None else float(lease_seconds)
            if not math.isfinite(duration) or duration <= 0:
                raise SharedPressureError("lease_seconds must be finite and positive")
            renewed = SharedPressureLease(lease.lease_id, lease.scope, lease.operation_id, lease.tenant_id, lease.owner_id, lease.priority, lease.acquired_at, timestamp + duration)
            conn.execute("UPDATE shared_pressure_lease SET expires_at = ? WHERE lease_id = ?", (renewed.expires_at, lease_id))
            return renewed

    def release(self, lease_id: str, owner_id: str) -> SharedPressureLease:
        lease_id, owner = _id(lease_id, "lease_id"), _id(owner_id, "owner_id")
        with self._write() as conn:
            row = conn.execute("SELECT * FROM shared_pressure_lease WHERE lease_id = ?", (lease_id,)).fetchone()
            if row is None:
                raise SharedPressureError("unknown pressure lease")
            lease = self._lease(row)
            if lease.owner_id != owner:
                raise SharedPressureConflict("pressure lease owner mismatch")
            conn.execute("DELETE FROM shared_pressure_lease WHERE lease_id = ?", (lease_id,))
            return lease

    def dequeue(self, ticket_id: str) -> SharedQueueTicket:
        ticket_id = _id(ticket_id, "ticket_id")
        with self._write() as conn:
            row = conn.execute("SELECT * FROM shared_pressure_queue WHERE ticket_id = ?", (ticket_id,)).fetchone()
            if row is None:
                raise SharedPressureError("unknown queue ticket")
            ticket = self._ticket(row)
            conn.execute("DELETE FROM shared_pressure_queue WHERE ticket_id = ?", (ticket_id,))
            return ticket

    def reap_expired(self, scope: str, *, now: float | None = None) -> int:
        scope, timestamp = _id(scope, "scope"), _time(now, "now")
        with self._write() as conn:
            self._policy_row(conn, scope)
            return self._reap(conn, scope, timestamp)


__all__ = [
    "SharedPressureConflict",
    "SharedPressureDecision",
    "SharedPressureError",
    "SharedPressureExceeded",
    "SharedPressureLease",
    "SharedPressurePolicy",
    "SharedPressureSnapshot",
    "SharedQueueTicket",
    "SqliteSharedPressureLedger",
]
