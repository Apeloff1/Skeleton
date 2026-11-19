"""Governed content addressing, cache identity, and saga durability.

P3-T2 storage invariants:

* Durable content is authoritative. Cache state may accelerate reads but can
  never be the sole copy of an object.
* Cache identity binds tenant, logical id, version, trust context and the
  authoritative content digest.
* Digest migration adds a new address while retaining old addresses as aliases;
  logical identity does not change.
* Saga compensation material is persisted before an external effect may be
  recorded as applied.
* Transaction strategy is explicit per operation: atomic, saga, or
  reconciliation. There is no implicit best-effort fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import sqlite3
import threading
from typing import Any, Callable, Iterable, Mapping, Sequence


SUPPORTED_DIGESTS = frozenset({"sha256", "sha512"})
MAX_ID = 512
MAX_TRUST_CONTEXT = 256
MAX_NAMESPACE = 128
MAX_RESOURCES = 256
MAX_COMPENSATION_BYTES = 1_048_576


class StorageContractError(ValueError):
    """A governed storage invariant was violated."""


def _text(value: object, field: str, *, maximum: int = MAX_ID) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StorageContractError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise StorageContractError(f"{field} exceeds maximum length")
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        raise StorageContractError(f"{field} contains unsafe characters")
    return value


def _positive_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StorageContractError("version must be a positive integer")
    return value


def _generation(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StorageContractError("generation must be a non-negative integer")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StorageContractError("value is not canonically serializable") from exc


def _digest(algorithm: str, payload: bytes) -> str:
    if algorithm not in SUPPORTED_DIGESTS:
        raise StorageContractError(f"unsupported digest algorithm: {algorithm}")
    return hashlib.new(algorithm, payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentDigest:
    algorithm: str
    value: str

    def __post_init__(self) -> None:
        if self.algorithm not in SUPPORTED_DIGESTS:
            raise StorageContractError("unsupported content digest algorithm")
        expected = hashlib.new(self.algorithm).digest_size * 2
        if (
            len(self.value) != expected
            or any(ch not in "0123456789abcdef" for ch in self.value)
        ):
            raise StorageContractError("content digest value is invalid")

    @property
    def address(self) -> str:
        return f"{self.algorithm}:{self.value}"


@dataclass(frozen=True, slots=True)
class DigestPolicy:
    current_algorithm: str = "sha256"
    accepted_algorithms: tuple[str, ...] = ("sha256",)

    def __post_init__(self) -> None:
        accepted = tuple(dict.fromkeys(self.accepted_algorithms))
        if self.current_algorithm not in SUPPORTED_DIGESTS:
            raise StorageContractError("current digest algorithm is unsupported")
        if not accepted or any(item not in SUPPORTED_DIGESTS for item in accepted):
            raise StorageContractError("accepted digest algorithm set is invalid")
        if self.current_algorithm not in accepted:
            raise StorageContractError("current digest must also be accepted")
        object.__setattr__(self, "accepted_algorithms", accepted)


@dataclass(frozen=True, slots=True)
class AddressedObject:
    tenant_id: str
    logical_id: str
    version: int
    trust_context: str
    digest: ContentDigest
    size_bytes: int


class TransactionMode(str, Enum):
    ATOMIC = "atomic"
    SAGA = "saga"
    RECONCILIATION = "reconciliation"


@dataclass(frozen=True, slots=True)
class TransactionPlan:
    operation_id: str
    tenant_id: str
    mode: TransactionMode
    resources: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id")
        _text(self.tenant_id, "tenant_id")
        try:
            mode = TransactionMode(self.mode)
        except ValueError as exc:
            raise StorageContractError("transaction mode is invalid") from exc
        object.__setattr__(self, "mode", mode)
        resources = tuple(dict.fromkeys(_text(item, "resource") for item in self.resources))
        if not resources or len(resources) > MAX_RESOURCES:
            raise StorageContractError("transaction resources are empty or exceed limit")
        object.__setattr__(self, "resources", resources)
        _text(self.rationale, "rationale", maximum=1024)


class GovernedContentStore:
    """SQLite-backed authoritative content store with digest migration aliases."""

    def __init__(
        self,
        path: str = ":memory:",
        *,
        digest_policy: DigestPolicy | None = None,
    ) -> None:
        self.digest_policy = digest_policy or DigestPolicy()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._db:
            self._db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS governed_object (
                    tenant_id TEXT NOT NULL,
                    logical_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    trust_context TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    PRIMARY KEY (tenant_id, logical_id, version)
                );
                CREATE TABLE IF NOT EXISTS governed_digest (
                    tenant_id TEXT NOT NULL,
                    logical_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    algorithm TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
                    PRIMARY KEY (tenant_id, logical_id, version, algorithm),
                    FOREIGN KEY (tenant_id, logical_id, version)
                      REFERENCES governed_object(tenant_id, logical_id, version)
                      ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_governed_digest_identity
                  ON governed_digest(tenant_id, logical_id, version, is_current);
                CREATE INDEX IF NOT EXISTS idx_governed_digest_address
                  ON governed_digest(tenant_id, algorithm, digest);
                """
            )

    def close(self) -> None:
        self._db.close()

    def put(
        self,
        *,
        tenant_id: str,
        logical_id: str,
        version: int,
        trust_context: str,
        payload: bytes | bytearray | memoryview | str | Mapping[str, Any] | Sequence[Any],
        canonicalizer: Callable[[object], bytes] | None = None,
    ) -> AddressedObject:
        tenant = _text(tenant_id, "tenant_id")
        logical = _text(logical_id, "logical_id")
        checked_version = _positive_version(version)
        trust = _text(trust_context, "trust_context", maximum=MAX_TRUST_CONTEXT)
        if canonicalizer is not None:
            raw = canonicalizer(payload)
            if not isinstance(raw, bytes):
                raise StorageContractError("canonicalizer must return bytes")
        elif isinstance(payload, bytes):
            raw = payload
        elif isinstance(payload, (bytearray, memoryview)):
            raw = bytes(payload)
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            raw = _canonical_json_bytes(payload)

        algorithm = self.digest_policy.current_algorithm
        digest_value = _digest(algorithm, raw)
        with self._lock, self._db:
            existing = self._db.execute(
                """
                SELECT trust_context, payload
                FROM governed_object
                WHERE tenant_id = ? AND logical_id = ? AND version = ?
                """,
                (tenant, logical, checked_version),
            ).fetchone()
            if existing is not None:
                if existing["trust_context"] != trust or bytes(existing["payload"]) != raw:
                    raise StorageContractError(
                        "logical identity/version cannot be rebound to different content"
                    )
                current = self._db.execute(
                    """
                    SELECT algorithm, digest
                    FROM governed_digest
                    WHERE tenant_id = ? AND logical_id = ? AND version = ?
                      AND is_current = 1
                    """,
                    (tenant, logical, checked_version),
                ).fetchone()
                if current is None:
                    raise StorageContractError(
                        "existing governed object is missing its current digest"
                    )
                return AddressedObject(
                    tenant_id=tenant,
                    logical_id=logical,
                    version=checked_version,
                    trust_context=trust,
                    digest=ContentDigest(current["algorithm"], current["digest"]),
                    size_bytes=len(raw),
                )
            self._db.execute(
                """
                INSERT INTO governed_object(
                    tenant_id, logical_id, version, trust_context, payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (tenant, logical, checked_version, trust, raw),
            )
            self._db.execute(
                """
                INSERT INTO governed_digest(
                    tenant_id, logical_id, version, algorithm, digest, is_current
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (tenant, logical, checked_version, algorithm, digest_value),
            )
        return AddressedObject(
            tenant_id=tenant,
            logical_id=logical,
            version=checked_version,
            trust_context=trust,
            digest=ContentDigest(algorithm, digest_value),
            size_bytes=len(raw),
        )

    def _object_row(
        self,
        *,
        tenant_id: str,
        logical_id: str,
        version: int,
    ) -> sqlite3.Row:
        row = self._db.execute(
            """
            SELECT o.*, d.algorithm, d.digest
            FROM governed_object AS o
            JOIN governed_digest AS d
              ON d.tenant_id = o.tenant_id
             AND d.logical_id = o.logical_id
             AND d.version = o.version
             AND d.is_current = 1
            WHERE o.tenant_id = ? AND o.logical_id = ? AND o.version = ?
            """,
            (
                _text(tenant_id, "tenant_id"),
                _text(logical_id, "logical_id"),
                _positive_version(version),
            ),
        ).fetchone()
        if row is None:
            raise KeyError("governed object not found")
        return row

    @staticmethod
    def _addressed(row: sqlite3.Row) -> AddressedObject:
        payload = bytes(row["payload"])
        return AddressedObject(
            tenant_id=row["tenant_id"],
            logical_id=row["logical_id"],
            version=int(row["version"]),
            trust_context=row["trust_context"],
            digest=ContentDigest(row["algorithm"], row["digest"]),
            size_bytes=len(payload),
        )

    def get(
        self,
        *,
        tenant_id: str,
        logical_id: str,
        version: int,
    ) -> tuple[AddressedObject, bytes]:
        with self._lock:
            row = self._object_row(
                tenant_id=tenant_id,
                logical_id=logical_id,
                version=version,
            )
            return self._addressed(row), bytes(row["payload"])

    def resolve(
        self,
        *,
        tenant_id: str,
        digest: ContentDigest,
    ) -> tuple[AddressedObject, bytes]:
        if digest.algorithm not in self.digest_policy.accepted_algorithms:
            raise StorageContractError("digest algorithm is not accepted by policy")
        tenant = _text(tenant_id, "tenant_id")
        with self._lock:
            rows = self._db.execute(
                """
                SELECT o.*, current.algorithm, current.digest
                FROM governed_digest AS requested
                JOIN governed_object AS o
                  ON o.tenant_id = requested.tenant_id
                 AND o.logical_id = requested.logical_id
                 AND o.version = requested.version
                JOIN governed_digest AS current
                  ON current.tenant_id = o.tenant_id
                 AND current.logical_id = o.logical_id
                 AND current.version = o.version
                 AND current.is_current = 1
                WHERE requested.tenant_id = ?
                  AND requested.algorithm = ?
                  AND requested.digest = ?
                ORDER BY o.logical_id, o.version
                """,
                (tenant, digest.algorithm, digest.value),
            ).fetchall()
            if not rows:
                raise KeyError("content address not found")
            identities = {
                (row["logical_id"], int(row["version"]), row["trust_context"])
                for row in rows
            }
            if len(identities) != 1:
                raise StorageContractError(
                    "content address is ambiguous across logical identities"
                )
            row = rows[0]
            return self._addressed(row), bytes(row["payload"])

    def migrate_digest(
        self,
        *,
        tenant_id: str,
        logical_id: str,
        version: int,
        to_algorithm: str,
    ) -> AddressedObject:
        if to_algorithm not in self.digest_policy.accepted_algorithms:
            raise StorageContractError("target digest algorithm is not accepted")
        with self._lock, self._db:
            row = self._object_row(
                tenant_id=tenant_id,
                logical_id=logical_id,
                version=version,
            )
            payload = bytes(row["payload"])
            migrated = _digest(to_algorithm, payload)
            self._db.execute(
                """
                UPDATE governed_digest
                SET is_current = 0
                WHERE tenant_id = ? AND logical_id = ? AND version = ?
                """,
                (row["tenant_id"], row["logical_id"], row["version"]),
            )
            self._db.execute(
                """
                INSERT INTO governed_digest(
                    tenant_id, logical_id, version, algorithm, digest, is_current
                ) VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(tenant_id, logical_id, version, algorithm)
                DO UPDATE SET digest = excluded.digest, is_current = 1
                """,
                (
                    row["tenant_id"],
                    row["logical_id"],
                    row["version"],
                    to_algorithm,
                    migrated,
                ),
            )
            return AddressedObject(
                tenant_id=row["tenant_id"],
                logical_id=row["logical_id"],
                version=int(row["version"]),
                trust_context=row["trust_context"],
                digest=ContentDigest(to_algorithm, migrated),
                size_bytes=len(payload),
            )


@dataclass(frozen=True, slots=True)
class CachePolicy:
    ttl_generations: int = 1
    stale_behavior: str = "miss"
    max_entries: int = 4096

    def __post_init__(self) -> None:
        ttl = _generation(self.ttl_generations)
        object.__setattr__(self, "ttl_generations", ttl)
        if self.stale_behavior not in {"miss", "rebuild"}:
            raise StorageContractError("stale_behavior must be miss or rebuild")
        if (
            isinstance(self.max_entries, bool)
            or not isinstance(self.max_entries, int)
            or self.max_entries < 1
            or self.max_entries > 100_000
        ):
            raise StorageContractError("max_entries must be between 1 and 100000")


@dataclass(frozen=True, slots=True)
class CacheKey:
    tenant_id: str
    namespace: str
    logical_id: str
    version: int
    trust_context: str
    authoritative_digest: ContentDigest

    def fingerprint(self) -> str:
        payload = {
            "tenant_id": _text(self.tenant_id, "tenant_id"),
            "namespace": _text(self.namespace, "namespace", maximum=MAX_NAMESPACE),
            "logical_id": _text(self.logical_id, "logical_id"),
            "version": _positive_version(self.version),
            "trust_context": _text(
                self.trust_context,
                "trust_context",
                maximum=MAX_TRUST_CONTEXT,
            ),
            "authoritative_digest": self.authoritative_digest.address,
        }
        return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    key: CacheKey
    payload: bytes
    stored_generation: int


class GovernedContentCache:
    """Non-authoritative cache that validates against the durable store."""

    def __init__(
        self,
        authority: GovernedContentStore,
        *,
        policy: CachePolicy | None = None,
    ) -> None:
        self.authority = authority
        self.policy = policy or CachePolicy()
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def _authoritative_key(
        self,
        *,
        tenant_id: str,
        namespace: str,
        logical_id: str,
        version: int,
    ) -> tuple[CacheKey, bytes]:
        obj, payload = self.authority.get(
            tenant_id=tenant_id,
            logical_id=logical_id,
            version=version,
        )
        return (
            CacheKey(
                tenant_id=obj.tenant_id,
                namespace=_text(namespace, "namespace", maximum=MAX_NAMESPACE),
                logical_id=obj.logical_id,
                version=obj.version,
                trust_context=obj.trust_context,
                authoritative_digest=obj.digest,
            ),
            payload,
        )

    def rebuild(
        self,
        *,
        tenant_id: str,
        namespace: str,
        logical_id: str,
        version: int,
        generation: int,
    ) -> CacheEntry:
        key, payload = self._authoritative_key(
            tenant_id=tenant_id,
            namespace=namespace,
            logical_id=logical_id,
            version=version,
        )
        entry = CacheEntry(key=key, payload=payload, stored_generation=_generation(generation))
        fingerprint = key.fingerprint()
        with self._lock:
            obsolete = [
                candidate
                for candidate, existing in self._entries.items()
                if existing.key.tenant_id == key.tenant_id
                and existing.key.namespace == key.namespace
                and existing.key.logical_id == key.logical_id
                and existing.key.version == key.version
                and candidate != fingerprint
            ]
            for candidate in obsolete:
                self._entries.pop(candidate, None)
            self._entries.pop(fingerprint, None)
            self._entries[fingerprint] = entry
            while len(self._entries) > self.policy.max_entries:
                oldest = next(iter(self._entries))
                self._entries.pop(oldest, None)
        return entry

    def get(
        self,
        *,
        tenant_id: str,
        namespace: str,
        logical_id: str,
        version: int,
        trust_context: str,
        generation: int,
    ) -> bytes | None:
        checked_generation = _generation(generation)
        try:
            current, authoritative_payload = self._authoritative_key(
                tenant_id=tenant_id,
                namespace=namespace,
                logical_id=logical_id,
                version=version,
            )
        except KeyError:
            return None
        if current.trust_context != _text(
            trust_context,
            "trust_context",
            maximum=MAX_TRUST_CONTEXT,
        ):
            return None
        fingerprint = current.fingerprint()
        with self._lock:
            entry = self._entries.get(fingerprint)
            if entry is not None:
                age = checked_generation - entry.stored_generation
                if age < 0:
                    self._entries.pop(fingerprint, None)
                    return None
                if (
                    age <= self.policy.ttl_generations
                    and entry.key.authoritative_digest == current.authoritative_digest
                    and entry.payload == authoritative_payload
                ):
                    return bytes(entry.payload)
                self._entries.pop(fingerprint, None)
        if self.policy.stale_behavior == "rebuild":
            return self.rebuild(
                tenant_id=tenant_id,
                namespace=namespace,
                logical_id=logical_id,
                version=version,
                generation=checked_generation,
            ).payload
        return None

    def invalidate(
        self,
        *,
        tenant_id: str,
        logical_id: str,
        version: int,
    ) -> int:
        tenant = _text(tenant_id, "tenant_id")
        logical = _text(logical_id, "logical_id")
        checked_version = _positive_version(version)
        with self._lock:
            doomed = [
                key
                for key, entry in self._entries.items()
                if entry.key.tenant_id == tenant
                and entry.key.logical_id == logical
                and entry.key.version == checked_version
            ]
            for key in doomed:
                self._entries.pop(key, None)
            return len(doomed)


@dataclass(frozen=True, slots=True)
class CompensationAction:
    """Executable recovery material for one applied saga effect."""

    index: int
    name: str
    compensation_ref: str
    compensation_payload: bytes
    effect_receipt: str


@dataclass(frozen=True, slots=True)
class SagaStepSnapshot:
    index: int
    name: str
    state: str
    compensation_ref: str
    effect_receipt: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class SagaSnapshot:
    saga_id: str
    tenant_id: str
    operation_id: str
    state: str
    steps: tuple[SagaStepSnapshot, ...]


class DurableSagaStateStore:
    """Durable compensation ledger; prepare must precede effect application."""

    STEP_STATES = frozenset({"prepared", "applied", "compensated", "failed"})
    SAGA_STATES = frozenset({"open", "compensating", "completed", "compensated", "failed"})

    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._db:
            self._db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS durable_saga (
                    saga_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS durable_saga_step (
                    saga_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    step_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    compensation_ref TEXT NOT NULL,
                    compensation_payload BLOB NOT NULL,
                    effect_receipt TEXT,
                    error TEXT,
                    PRIMARY KEY (saga_id, step_index),
                    FOREIGN KEY (saga_id) REFERENCES durable_saga(saga_id)
                      ON DELETE CASCADE
                );
                """
            )

    def begin(self, *, saga_id: str, tenant_id: str, operation_id: str) -> None:
        sid = _text(saga_id, "saga_id")
        tenant = _text(tenant_id, "tenant_id")
        operation = _text(operation_id, "operation_id")
        with self._lock, self._db:
            try:
                self._db.execute(
                    "INSERT INTO durable_saga(saga_id, tenant_id, operation_id, state) VALUES (?, ?, ?, 'open')",
                    (sid, tenant, operation),
                )
            except sqlite3.IntegrityError as exc:
                raise StorageContractError("saga id already exists") from exc

    def prepare_step(
        self,
        *,
        saga_id: str,
        index: int,
        name: str,
        compensation_ref: str,
        compensation_payload: bytes | str | Mapping[str, Any],
    ) -> None:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise StorageContractError("saga step index must be a non-negative integer")
        sid = _text(saga_id, "saga_id")
        step_name = _text(name, "step name")
        compensation = _text(compensation_ref, "compensation_ref")
        if isinstance(compensation_payload, bytes):
            payload = compensation_payload
        elif isinstance(compensation_payload, str):
            payload = compensation_payload.encode("utf-8")
        else:
            payload = _canonical_json_bytes(compensation_payload)
        if len(payload) > MAX_COMPENSATION_BYTES:
            raise StorageContractError("compensation payload exceeds maximum bytes")
        with self._lock, self._db:
            saga = self._db.execute(
                "SELECT state FROM durable_saga WHERE saga_id = ?",
                (sid,),
            ).fetchone()
            if saga is None:
                raise KeyError("saga not found")
            if saga["state"] != "open":
                raise StorageContractError("cannot prepare step on non-open saga")
            try:
                self._db.execute(
                    """
                    INSERT INTO durable_saga_step(
                        saga_id, step_index, step_name, state,
                        compensation_ref, compensation_payload
                    ) VALUES (?, ?, ?, 'prepared', ?, ?)
                    """,
                    (sid, index, step_name, compensation, payload),
                )
            except sqlite3.IntegrityError as exc:
                raise StorageContractError("saga step already prepared") from exc

    def mark_effect_applied(
        self,
        *,
        saga_id: str,
        index: int,
        effect_receipt: str,
    ) -> None:
        sid = _text(saga_id, "saga_id")
        receipt = _text(effect_receipt, "effect_receipt", maximum=1024)
        with self._lock, self._db:
            saga = self._db.execute(
                "SELECT state FROM durable_saga WHERE saga_id = ?",
                (sid,),
            ).fetchone()
            if saga is None:
                raise KeyError("saga not found")
            if saga["state"] != "open":
                raise StorageContractError("effect can only apply while saga is open")
            row = self._db.execute(
                "SELECT state FROM durable_saga_step WHERE saga_id = ? AND step_index = ?",
                (sid, index),
            ).fetchone()
            if row is None:
                raise StorageContractError(
                    "compensation state must be prepared before effect application"
                )
            if row["state"] != "prepared":
                raise StorageContractError("effect can only apply from prepared state")
            self._db.execute(
                """
                UPDATE durable_saga_step
                SET state = 'applied', effect_receipt = ?
                WHERE saga_id = ? AND step_index = ?
                """,
                (receipt, sid, index),
            )

    def begin_compensation(self, *, saga_id: str) -> None:
        sid = _text(saga_id, "saga_id")
        with self._lock, self._db:
            updated = self._db.execute(
                "UPDATE durable_saga SET state = 'compensating' WHERE saga_id = ? AND state = 'open'",
                (sid,),
            ).rowcount
            if updated != 1:
                raise StorageContractError("saga cannot enter compensation")

    def pending_compensations(self, *, saga_id: str) -> tuple[CompensationAction, ...]:
        """Return outstanding compensation work in reverse effect order."""
        sid = _text(saga_id, "saga_id")
        with self._lock:
            saga = self._db.execute(
                "SELECT state FROM durable_saga WHERE saga_id = ?",
                (sid,),
            ).fetchone()
            if saga is None:
                raise KeyError("saga not found")
            if saga["state"] != "compensating":
                raise StorageContractError(
                    "pending compensations are available only while saga is compensating"
                )
            rows = self._db.execute(
                """
                SELECT step_index, step_name, compensation_ref,
                       compensation_payload, effect_receipt
                FROM durable_saga_step
                WHERE saga_id = ? AND state = 'applied'
                ORDER BY step_index DESC
                """,
                (sid,),
            ).fetchall()
        return tuple(
            CompensationAction(
                index=int(row["step_index"]),
                name=row["step_name"],
                compensation_ref=row["compensation_ref"],
                compensation_payload=bytes(row["compensation_payload"]),
                effect_receipt=row["effect_receipt"],
            )
            for row in rows
        )

    def mark_compensated(self, *, saga_id: str, index: int) -> None:
        sid = _text(saga_id, "saga_id")
        with self._lock, self._db:
            saga = self._db.execute(
                "SELECT state FROM durable_saga WHERE saga_id = ?",
                (sid,),
            ).fetchone()
            if saga is None:
                raise KeyError("saga not found")
            if saga["state"] != "compensating":
                raise StorageContractError(
                    "effects can only be compensated while saga is compensating"
                )
            row = self._db.execute(
                "SELECT state FROM durable_saga_step WHERE saga_id = ? AND step_index = ?",
                (sid, index),
            ).fetchone()
            if row is None or row["state"] != "applied":
                raise StorageContractError("only applied effects can be compensated")
            self._db.execute(
                "UPDATE durable_saga_step SET state = 'compensated' WHERE saga_id = ? AND step_index = ?",
                (sid, index),
            )

    def finish(self, *, saga_id: str, state: str) -> None:
        if state not in {"completed", "compensated", "failed"}:
            raise StorageContractError("invalid terminal saga state")
        sid = _text(saga_id, "saga_id")
        with self._lock, self._db:
            saga = self._db.execute(
                "SELECT state FROM durable_saga WHERE saga_id = ?",
                (sid,),
            ).fetchone()
            if saga is None:
                raise KeyError("saga not found")
            current_state = saga["state"]
            allowed_from = {
                "completed": {"open"},
                "compensated": {"compensating"},
                "failed": {"open", "compensating"},
            }
            if current_state not in allowed_from[state]:
                raise StorageContractError(
                    f"saga cannot transition from {current_state} to {state}"
                )
            if state == "completed":
                unresolved = self._db.execute(
                    """
                    SELECT COUNT(*) AS n FROM durable_saga_step
                    WHERE saga_id = ? AND state != 'applied'
                    """,
                    (sid,),
                ).fetchone()["n"]
                if unresolved:
                    raise StorageContractError(
                        "completed saga requires every prepared step to be applied"
                    )
            if state == "compensated":
                unresolved = self._db.execute(
                    """
                    SELECT COUNT(*) AS n FROM durable_saga_step
                    WHERE saga_id = ? AND state = 'applied'
                    """,
                    (sid,),
                ).fetchone()["n"]
                if unresolved:
                    raise StorageContractError(
                        "compensated saga still has uncompensated applied effects"
                    )
            self._db.execute(
                "UPDATE durable_saga SET state = ? WHERE saga_id = ?",
                (state, sid),
            )

    def snapshot(self, *, saga_id: str) -> SagaSnapshot:
        sid = _text(saga_id, "saga_id")
        with self._lock:
            saga = self._db.execute(
                "SELECT * FROM durable_saga WHERE saga_id = ?",
                (sid,),
            ).fetchone()
            if saga is None:
                raise KeyError("saga not found")
            rows = self._db.execute(
                """
                SELECT step_index, step_name, state, compensation_ref,
                       effect_receipt, error
                FROM durable_saga_step
                WHERE saga_id = ?
                ORDER BY step_index
                """,
                (sid,),
            ).fetchall()
        return SagaSnapshot(
            saga_id=saga["saga_id"],
            tenant_id=saga["tenant_id"],
            operation_id=saga["operation_id"],
            state=saga["state"],
            steps=tuple(
                SagaStepSnapshot(
                    index=int(row["step_index"]),
                    name=row["step_name"],
                    state=row["state"],
                    compensation_ref=row["compensation_ref"],
                    effect_receipt=row["effect_receipt"],
                    error=row["error"],
                )
                for row in rows
            ),
        )


__all__ = [
    "AddressedObject",
    "CacheEntry",
    "CacheKey",
    "CachePolicy",
    "CompensationAction",
    "ContentDigest",
    "DigestPolicy",
    "DurableSagaStateStore",
    "GovernedContentCache",
    "GovernedContentStore",
    "SagaSnapshot",
    "SagaStepSnapshot",
    "StorageContractError",
    "TransactionMode",
    "TransactionPlan",
]
