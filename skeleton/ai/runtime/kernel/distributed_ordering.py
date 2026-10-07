"""Durable distributed time, lease, fencing, and ordering authority for G010.

The existing kernel has useful in-process vector clocks and lease helpers. This
module defines the missing cross-process contract: workers coordinate through
one durable authority whose hybrid logical clock, fencing generations, lease
identity, and accepted-effect order survive process restart.

This is deliberately not a consensus implementation. A deployment may back
the same semantics with a consensus database or another linearizable store.
The SQLite implementation is a reference authority for one shared durable
coordination domain and fails closed if that authority is unavailable or
corrupt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any


_INT64_MAX = (1 << 63) - 1
_MAX_TTL_NS = 30 * 24 * 60 * 60 * 1_000_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DistributedOrderingError(RuntimeError):
    """Base distributed ordering/lease authority failure."""


class DistributedStateCorruption(DistributedOrderingError):
    """Persisted coordination state cannot be trusted."""


class LeaseConflict(DistributedOrderingError):
    """A live lease or its exact identity conflicts with the request."""


class LeaseExpired(DistributedOrderingError):
    """The caller's lease no longer grants authority."""


class StaleFence(DistributedOrderingError):
    """A fence token is older than the current resource generation."""


class OrderingConflict(DistributedOrderingError):
    """An effect violates exact-next or idempotency ordering."""


def _text(value: object, field: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DistributedOrderingError(f"{field} must be canonical non-empty text")
    if len(value) > max_length:
        raise DistributedOrderingError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise DistributedOrderingError(f"{field} contains control characters")
    return value


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _INT64_MAX,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise DistributedOrderingError(
            f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DistributedOrderingError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


@dataclass(frozen=True, slots=True)
class HybridTime:
    physical_ns: int
    logical: int
    order_index: int

    def as_dict(self) -> dict[str, int]:
        return {
            "physical_ns": self.physical_ns,
            "logical": self.logical,
            "order_index": self.order_index,
        }


@dataclass(frozen=True, slots=True)
class LeaseGrant:
    namespace: str
    tenant_id: str
    resource_id: str
    holder_id: str
    lease_id: str
    fence: int
    version: int
    granted_time: HybridTime
    expires_physical_ns: int

    def is_live_at(self, physical_ns: int) -> bool:
        return physical_ns < self.expires_physical_ns

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "holder_id": self.holder_id,
            "lease_id": self.lease_id,
            "fence": self.fence,
            "version": self.version,
            "granted_time": self.granted_time.as_dict(),
            "expires_physical_ns": self.expires_physical_ns,
        }


@dataclass(frozen=True, slots=True)
class EffectReceipt:
    namespace: str
    tenant_id: str
    resource_id: str
    lease_id: str
    holder_id: str
    fence: int
    sequence: int
    effect_id: str
    effect_digest: str
    accepted_time: HybridTime

    def as_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "lease_id": self.lease_id,
            "holder_id": self.holder_id,
            "fence": self.fence,
            "sequence": self.sequence,
            "effect_id": self.effect_id,
            "effect_digest": self.effect_digest,
            "accepted_time": self.accepted_time.as_dict(),
        }


class SQLiteDistributedOrdering:
    """Shared durable coordination authority with HLC time and fencing."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "distributed_ordering",
    ) -> None:
        self.namespace = _text(namespace, "namespace")
        self._connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS distributed_clock (
                    namespace TEXT PRIMARY KEY,
                    physical_ns INTEGER NOT NULL,
                    logical INTEGER NOT NULL,
                    order_index INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS distributed_lease (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    holder_id TEXT,
                    lease_id TEXT,
                    fence INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    granted_physical_ns INTEGER NOT NULL,
                    granted_logical INTEGER NOT NULL,
                    granted_order_index INTEGER NOT NULL,
                    expires_physical_ns INTEGER NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, resource_id)
                );

                CREATE TABLE IF NOT EXISTS distributed_effect (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    holder_id TEXT NOT NULL,
                    fence INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    effect_id TEXT NOT NULL,
                    effect_digest TEXT NOT NULL,
                    physical_ns INTEGER NOT NULL,
                    logical INTEGER NOT NULL,
                    order_index INTEGER NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, resource_id, fence, sequence),
                    UNIQUE(namespace, tenant_id, effect_id),
                    UNIQUE(namespace, order_index)
                );
                """
            )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO distributed_clock(
                    namespace, physical_ns, logical, order_index
                ) VALUES (?, 0, 0, 0)
                """,
                (self.namespace,),
            )

    def acquire(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        holder_id: str,
        lease_id: str,
        ttl_ns: int,
        now_ns: int | None = None,
    ) -> LeaseGrant:
        tenant = _text(tenant_id, "tenant_id")
        resource = _text(resource_id, "resource_id")
        holder = _text(holder_id, "holder_id")
        lease = _text(lease_id, "lease_id")
        ttl = _integer(ttl_ns, "ttl_ns", minimum=1, maximum=_MAX_TTL_NS)
        observed = self._observed_ns(now_ns)

        with self._lock:
            self._begin()
            try:
                mark = self._advance_clock(observed)
                row = self._lease_row(tenant, resource)
                if row is None:
                    fence = 1
                    version = 1
                else:
                    state = self._lease_from_row(row, require_holder=False)
                    if state is not None and state.is_live_at(mark.physical_ns):
                        if state.holder_id == holder and state.lease_id == lease:
                            self._commit()
                            return state
                        raise LeaseConflict("resource has a live lease")
                    fence = _integer(
                        row["fence"], "persisted fence", minimum=0
                    ) + 1
                    version = _integer(
                        row["version"], "persisted version", minimum=0
                    ) + 1
                    if fence > _INT64_MAX or version > _INT64_MAX:
                        raise DistributedStateCorruption("lease counter exhausted")

                expires = self._expiry(mark.physical_ns, ttl)
                self._connection.execute(
                    """
                    INSERT INTO distributed_lease(
                        namespace, tenant_id, resource_id, holder_id, lease_id,
                        fence, version, granted_physical_ns, granted_logical,
                        granted_order_index, expires_physical_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, tenant_id, resource_id)
                    DO UPDATE SET
                        holder_id = excluded.holder_id,
                        lease_id = excluded.lease_id,
                        fence = excluded.fence,
                        version = excluded.version,
                        granted_physical_ns = excluded.granted_physical_ns,
                        granted_logical = excluded.granted_logical,
                        granted_order_index = excluded.granted_order_index,
                        expires_physical_ns = excluded.expires_physical_ns
                    """,
                    (
                        self.namespace,
                        tenant,
                        resource,
                        holder,
                        lease,
                        fence,
                        version,
                        mark.physical_ns,
                        mark.logical,
                        mark.order_index,
                        expires,
                    ),
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return LeaseGrant(
            namespace=self.namespace,
            tenant_id=tenant,
            resource_id=resource,
            holder_id=holder,
            lease_id=lease,
            fence=fence,
            version=version,
            granted_time=mark,
            expires_physical_ns=expires,
        )

    def renew(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        holder_id: str,
        lease_id: str,
        expected_fence: int,
        ttl_ns: int,
        now_ns: int | None = None,
    ) -> LeaseGrant:
        tenant = _text(tenant_id, "tenant_id")
        resource = _text(resource_id, "resource_id")
        holder = _text(holder_id, "holder_id")
        lease = _text(lease_id, "lease_id")
        fence = _integer(expected_fence, "expected_fence", minimum=1)
        ttl = _integer(ttl_ns, "ttl_ns", minimum=1, maximum=_MAX_TTL_NS)
        observed = self._observed_ns(now_ns)

        with self._lock:
            self._begin()
            try:
                mark = self._advance_clock(observed)
                current = self._require_live_lease(
                    tenant, resource, holder, lease, fence, mark.physical_ns
                )
                version = current.version + 1
                if version > _INT64_MAX:
                    raise DistributedStateCorruption("lease version exhausted")
                expires = self._expiry(mark.physical_ns, ttl)
                cursor = self._connection.execute(
                    """
                    UPDATE distributed_lease
                    SET version = ?, expires_physical_ns = ?
                    WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                      AND holder_id = ? AND lease_id = ? AND fence = ?
                      AND version = ?
                    """,
                    (
                        version,
                        expires,
                        self.namespace,
                        tenant,
                        resource,
                        holder,
                        lease,
                        fence,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LeaseConflict("lease renewal lost authority race")
                self._commit()
            except Exception:
                self._rollback()
                raise
        return LeaseGrant(
            namespace=current.namespace,
            tenant_id=current.tenant_id,
            resource_id=current.resource_id,
            holder_id=current.holder_id,
            lease_id=current.lease_id,
            fence=current.fence,
            version=version,
            granted_time=current.granted_time,
            expires_physical_ns=expires,
        )

    def release(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        holder_id: str,
        lease_id: str,
        expected_fence: int,
        now_ns: int | None = None,
    ) -> HybridTime:
        tenant = _text(tenant_id, "tenant_id")
        resource = _text(resource_id, "resource_id")
        holder = _text(holder_id, "holder_id")
        lease = _text(lease_id, "lease_id")
        fence = _integer(expected_fence, "expected_fence", minimum=1)
        observed = self._observed_ns(now_ns)

        with self._lock:
            self._begin()
            try:
                mark = self._advance_clock(observed)
                current = self._require_live_lease(
                    tenant, resource, holder, lease, fence, mark.physical_ns
                )
                version = current.version + 1
                cursor = self._connection.execute(
                    """
                    UPDATE distributed_lease
                    SET holder_id = NULL, lease_id = NULL, version = ?,
                        expires_physical_ns = ?
                    WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                      AND holder_id = ? AND lease_id = ? AND fence = ?
                      AND version = ?
                    """,
                    (
                        version,
                        mark.physical_ns,
                        self.namespace,
                        tenant,
                        resource,
                        holder,
                        lease,
                        fence,
                        current.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LeaseConflict("lease release lost authority race")
                self._commit()
            except Exception:
                self._rollback()
                raise
        return mark

    def current(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        now_ns: int | None = None,
    ) -> LeaseGrant | None:
        tenant = _text(tenant_id, "tenant_id")
        resource = _text(resource_id, "resource_id")
        observed = self._observed_ns(now_ns)
        with self._lock:
            self._begin()
            try:
                mark = self._advance_clock(observed)
                row = self._lease_row(tenant, resource)
                state = (
                    None
                    if row is None
                    else self._lease_from_row(row, require_holder=False)
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        if state is None or not state.is_live_at(mark.physical_ns):
            return None
        return state

    def accept_effect(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        holder_id: str,
        lease_id: str,
        fence: int,
        sequence: int,
        effect_id: str,
        effect_digest: str,
        now_ns: int | None = None,
    ) -> EffectReceipt:
        tenant = _text(tenant_id, "tenant_id")
        resource = _text(resource_id, "resource_id")
        holder = _text(holder_id, "holder_id")
        lease = _text(lease_id, "lease_id")
        expected_fence = _integer(fence, "fence", minimum=1)
        expected_sequence = _integer(sequence, "sequence", minimum=1)
        eid = _text(effect_id, "effect_id")
        payload = _digest(effect_digest, "effect_digest")
        observed = self._observed_ns(now_ns)

        with self._lock:
            self._begin()
            try:
                replay = self._effect_by_id(tenant, eid)
                if replay is not None:
                    receipt = self._effect_from_row(replay)
                    if (
                        receipt.resource_id != resource
                        or receipt.holder_id != holder
                        or receipt.lease_id != lease
                        or receipt.fence != expected_fence
                        or receipt.sequence != expected_sequence
                        or receipt.effect_digest != payload
                    ):
                        raise OrderingConflict(
                            "effect_id replay changed effect identity"
                        )
                    self._commit()
                    return receipt

                mark = self._advance_clock(observed)
                self._require_live_lease(
                    tenant,
                    resource,
                    holder,
                    lease,
                    expected_fence,
                    mark.physical_ns,
                )
                last = self._connection.execute(
                    """
                    SELECT MAX(sequence) AS n
                    FROM distributed_effect
                    WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                      AND fence = ?
                    """,
                    (self.namespace, tenant, resource, expected_fence),
                ).fetchone()
                prior = 0 if last["n"] is None else _integer(
                    last["n"], "persisted effect sequence", minimum=1
                )
                if expected_sequence != prior + 1:
                    raise OrderingConflict(
                        f"effect sequence must be exact-next {prior + 1}"
                    )
                self._connection.execute(
                    """
                    INSERT INTO distributed_effect(
                        namespace, tenant_id, resource_id, lease_id, holder_id,
                        fence, sequence, effect_id, effect_digest,
                        physical_ns, logical, order_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        tenant,
                        resource,
                        lease,
                        holder,
                        expected_fence,
                        expected_sequence,
                        eid,
                        payload,
                        mark.physical_ns,
                        mark.logical,
                        mark.order_index,
                    ),
                )
                self._commit()
            except Exception:
                self._rollback()
                raise
        return EffectReceipt(
            namespace=self.namespace,
            tenant_id=tenant,
            resource_id=resource,
            lease_id=lease,
            holder_id=holder,
            fence=expected_fence,
            sequence=expected_sequence,
            effect_id=eid,
            effect_digest=payload,
            accepted_time=mark,
        )

    def effects(
        self,
        *,
        tenant_id: str,
        resource_id: str,
    ) -> tuple[EffectReceipt, ...]:
        tenant = _text(tenant_id, "tenant_id")
        resource = _text(resource_id, "resource_id")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT *
                FROM distributed_effect
                WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
                ORDER BY order_index ASC
                """,
                (self.namespace, tenant, resource),
            ).fetchall()
        receipts = tuple(self._effect_from_row(row) for row in rows)
        by_fence: dict[int, int] = {}
        last_order = 0
        for receipt in receipts:
            if receipt.accepted_time.order_index <= last_order:
                raise DistributedStateCorruption("effect order_index is not monotonic")
            last_order = receipt.accepted_time.order_index
            prior = by_fence.get(receipt.fence, 0)
            if receipt.sequence != prior + 1:
                raise DistributedStateCorruption(
                    "persisted effect sequence is not contiguous"
                )
            by_fence[receipt.fence] = receipt.sequence
        return receipts

    def clock(self) -> HybridTime:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT physical_ns, logical, order_index
                FROM distributed_clock WHERE namespace = ?
                """,
                (self.namespace,),
            ).fetchone()
        if row is None:
            raise DistributedStateCorruption("distributed clock is missing")
        return self._mark_from_row(row)

    def card(self) -> dict[str, Any]:
        with self._lock:
            leases = self._connection.execute(
                "SELECT COUNT(*) AS n FROM distributed_lease WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
            effects = self._connection.execute(
                "SELECT COUNT(*) AS n FROM distributed_effect WHERE namespace = ?",
                (self.namespace,),
            ).fetchone()
        mark = self.clock()
        return {
            "kind": "distributed_ordering_authority",
            "gap": "G010",
            "law": "durable-hlc-lease-fence-exact-next",
            "resource_count": int(leases["n"]),
            "effect_count": int(effects["n"]),
            "clock": mark.as_dict(),
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _observed_ns(self, value: int | None) -> int:
        observed = time.time_ns() if value is None else value
        return _integer(observed, "now_ns", minimum=1)

    def _expiry(self, physical_ns: int, ttl_ns: int) -> int:
        if physical_ns > _INT64_MAX - ttl_ns:
            raise DistributedOrderingError("lease expiry exceeds durable range")
        return physical_ns + ttl_ns

    def _begin(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._connection.execute("COMMIT")

    def _rollback(self) -> None:
        self._connection.execute("ROLLBACK")

    def _advance_clock(self, observed_ns: int) -> HybridTime:
        row = self._connection.execute(
            """
            SELECT physical_ns, logical, order_index
            FROM distributed_clock WHERE namespace = ?
            """,
            (self.namespace,),
        ).fetchone()
        if row is None:
            raise DistributedStateCorruption("distributed clock is missing")
        prior = self._mark_from_row(row)
        if observed_ns > prior.physical_ns:
            physical = observed_ns
            logical = 0
        else:
            physical = prior.physical_ns
            logical = prior.logical + 1
        order_index = prior.order_index + 1
        if logical > _INT64_MAX or order_index > _INT64_MAX:
            raise DistributedStateCorruption("distributed clock exhausted")
        cursor = self._connection.execute(
            """
            UPDATE distributed_clock
            SET physical_ns = ?, logical = ?, order_index = ?
            WHERE namespace = ? AND physical_ns = ? AND logical = ?
              AND order_index = ?
            """,
            (
                physical,
                logical,
                order_index,
                self.namespace,
                prior.physical_ns,
                prior.logical,
                prior.order_index,
            ),
        )
        if cursor.rowcount != 1:
            raise DistributedOrderingError("distributed clock advance lost race")
        return HybridTime(physical, logical, order_index)

    def _mark_from_row(self, row: sqlite3.Row) -> HybridTime:
        try:
            return HybridTime(
                physical_ns=_integer(
                    row["physical_ns"], "persisted physical_ns", minimum=0
                ),
                logical=_integer(row["logical"], "persisted logical", minimum=0),
                order_index=_integer(
                    row["order_index"], "persisted order_index", minimum=0
                ),
            )
        except DistributedOrderingError as exc:
            raise DistributedStateCorruption("persisted clock is invalid") from exc

    def _lease_row(self, tenant_id: str, resource_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT *
            FROM distributed_lease
            WHERE namespace = ? AND tenant_id = ? AND resource_id = ?
            """,
            (self.namespace, tenant_id, resource_id),
        ).fetchone()

    def _lease_from_row(
        self,
        row: sqlite3.Row,
        *,
        require_holder: bool,
    ) -> LeaseGrant | None:
        holder = row["holder_id"]
        lease_id = row["lease_id"]
        if holder is None or lease_id is None:
            if holder is not None or lease_id is not None:
                raise DistributedStateCorruption(
                    "released lease has partial holder identity"
                )
            if require_holder:
                raise LeaseExpired("resource has no live lease identity")
            self._validate_lease_counters(row)
            return None
        try:
            grant = LeaseGrant(
                namespace=self.namespace,
                tenant_id=_text(row["tenant_id"], "persisted tenant_id"),
                resource_id=_text(row["resource_id"], "persisted resource_id"),
                holder_id=_text(holder, "persisted holder_id"),
                lease_id=_text(lease_id, "persisted lease_id"),
                fence=_integer(row["fence"], "persisted fence", minimum=1),
                version=_integer(row["version"], "persisted version", minimum=1),
                granted_time=HybridTime(
                    _integer(
                        row["granted_physical_ns"],
                        "persisted granted_physical_ns",
                        minimum=1,
                    ),
                    _integer(
                        row["granted_logical"],
                        "persisted granted_logical",
                        minimum=0,
                    ),
                    _integer(
                        row["granted_order_index"],
                        "persisted granted_order_index",
                        minimum=1,
                    ),
                ),
                expires_physical_ns=_integer(
                    row["expires_physical_ns"],
                    "persisted expires_physical_ns",
                    minimum=1,
                ),
            )
        except DistributedOrderingError as exc:
            raise DistributedStateCorruption("persisted lease is invalid") from exc
        if grant.expires_physical_ns <= grant.granted_time.physical_ns:
            raise DistributedStateCorruption("persisted lease expiry is invalid")
        return grant

    def _validate_lease_counters(self, row: sqlite3.Row) -> None:
        try:
            _integer(row["fence"], "persisted fence", minimum=1)
            _integer(row["version"], "persisted version", minimum=1)
            _integer(
                row["expires_physical_ns"],
                "persisted expires_physical_ns",
                minimum=1,
            )
        except DistributedOrderingError as exc:
            raise DistributedStateCorruption("persisted lease is invalid") from exc

    def _require_live_lease(
        self,
        tenant_id: str,
        resource_id: str,
        holder_id: str,
        lease_id: str,
        expected_fence: int,
        physical_ns: int,
    ) -> LeaseGrant:
        row = self._lease_row(tenant_id, resource_id)
        if row is None:
            raise LeaseExpired("resource has no lease")
        current = self._lease_from_row(row, require_holder=True)
        assert current is not None
        if expected_fence < current.fence:
            raise StaleFence("stale fencing token")
        if expected_fence > current.fence:
            raise LeaseConflict("future fencing token")
        if current.holder_id != holder_id or current.lease_id != lease_id:
            raise LeaseConflict("lease identity mismatch")
        if not current.is_live_at(physical_ns):
            raise LeaseExpired("lease expired")
        return current

    def _effect_by_id(self, tenant_id: str, effect_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT *
            FROM distributed_effect
            WHERE namespace = ? AND tenant_id = ? AND effect_id = ?
            """,
            (self.namespace, tenant_id, effect_id),
        ).fetchone()

    def _effect_from_row(self, row: sqlite3.Row) -> EffectReceipt:
        try:
            return EffectReceipt(
                namespace=self.namespace,
                tenant_id=_text(row["tenant_id"], "persisted tenant_id"),
                resource_id=_text(row["resource_id"], "persisted resource_id"),
                lease_id=_text(row["lease_id"], "persisted lease_id"),
                holder_id=_text(row["holder_id"], "persisted holder_id"),
                fence=_integer(row["fence"], "persisted fence", minimum=1),
                sequence=_integer(
                    row["sequence"], "persisted sequence", minimum=1
                ),
                effect_id=_text(row["effect_id"], "persisted effect_id"),
                effect_digest=_digest(
                    row["effect_digest"], "persisted effect_digest"
                ),
                accepted_time=HybridTime(
                    _integer(
                        row["physical_ns"], "persisted physical_ns", minimum=1
                    ),
                    _integer(row["logical"], "persisted logical", minimum=0),
                    _integer(
                        row["order_index"], "persisted order_index", minimum=1
                    ),
                ),
            )
        except DistributedOrderingError as exc:
            raise DistributedStateCorruption("persisted effect is invalid") from exc

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteDistributedOrdering":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
