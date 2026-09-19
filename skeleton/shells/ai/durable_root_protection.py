"""Durable external-reference holds for historical evidence-chain roots.

Hash-linked journal and receipt chains can contain structurally valid nodes that
are unreachable from the current head after a lost CAS race.  Chain-local
orphan detection is intentionally conservative, but it cannot know whether an
apparently unreachable historical root has already been committed into another
durable evidence object.

This registry provides that missing cross-store authority.  One CAS-updated
record per (chain_id, root_hash) contains the complete bounded claim set, so
there is no two-record crash window where a claim exists but the GC lookup
index does not.  Claims may be permanent or time-bounded.  Removing a claim is
explicit and generation-monotonic; empty tombstone records are retained to
avoid ABA-style ambiguity.

The registry does not make a root valid or reachable.  It only means destructive
maintenance must not delete that root while at least one live claim exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(
            f"{name} must be 64-character digest"
        )
    return value.lower()


def _timestamp(
    name: str,
    value: float,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(
            f"{name} must be finite and non-negative"
        )
    return float(value)


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class DurableRootProtectionKind(str, Enum):
    FINALIZATION = "finalization"
    RECOVERY_CHECKPOINT = "recovery_checkpoint"
    SESSION_COMMIT = "session_commit"
    ARCHIVE = "archive"
    HOT_FLOOR = "hot_floor"
    RETENTION = "retention"
    OPERATOR_HOLD = "operator_hold"


@dataclass(frozen=True)
class DurableRootProtectionClaim:
    schema_version: int
    claim_id: str
    chain_id: str
    root_hash: str
    kind: DurableRootProtectionKind
    source_id: str
    source_digest: str
    created_at: float
    expires_at: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported root protection claim schema"
            )
        object.__setattr__(
            self,
            "claim_id",
            _digest("claim_id", self.claim_id),
        )
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        object.__setattr__(
            self,
            "kind",
            DurableRootProtectionKind(
                self.kind
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _identity(
                "source_id",
                self.source_id,
                maximum=256,
            ),
        )
        object.__setattr__(
            self,
            "source_digest",
            _digest(
                "source_digest",
                self.source_digest,
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            _timestamp(
                "created_at",
                self.created_at,
            ),
        )
        object.__setattr__(
            self,
            "expires_at",
            _timestamp(
                "expires_at",
                self.expires_at,
            ),
        )
        if (
            self.expires_at
            and self.expires_at <= self.created_at
        ):
            raise ValueError(
                "root protection expiry must follow creation"
            )
        if (
            not isinstance(self.reason, str)
            or len(self.reason) > 2048
        ):
            raise ValueError(
                "root protection reason too long"
            )
        expected = self.derive_id(
            chain_id=self.chain_id,
            root_hash=self.root_hash,
            kind=self.kind,
            source_id=self.source_id,
            source_digest=self.source_digest,
        )
        if self.claim_id != expected:
            raise ValueError(
                "root protection claim_id differs from stable identity"
            )

    @staticmethod
    def derive_id(
        *,
        chain_id: str,
        root_hash: str,
        kind: DurableRootProtectionKind,
        source_id: str,
        source_digest: str,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        kind = DurableRootProtectionKind(kind)
        source_id = _identity(
            "source_id",
            source_id,
            maximum=256,
        )
        source_digest = _digest(
            "source_digest",
            source_digest,
        )
        return _stable_digest(
            {
                "chain_id": chain_id,
                "root_hash": root_hash,
                "kind": kind.value,
                "source_id": source_id,
                "source_digest": source_digest,
                "authority": (
                    "durable-root-protection"
                ),
            }
        )

    def active(
        self,
        now: float,
    ) -> bool:
        now = _timestamp("now", now)
        return (
            self.expires_at == 0.0
            or now < self.expires_at
        )

    @property
    def permanent(self) -> bool:
        return self.expires_at == 0.0

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "chain_id": self.chain_id,
            "root_hash": self.root_hash,
            "kind": self.kind.value,
            "source_id": self.source_id,
            "source_digest": self.source_digest,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "permanent": self.permanent,
            "reason": self.reason,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableProtectedRoot:
    schema_version: int
    chain_id: str
    root_hash: str
    generation: int
    claims: tuple[DurableRootProtectionClaim, ...]
    updated_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported protected root schema"
            )
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(
                self.generation,
                int,
            )
            or self.generation <= 0
        ):
            raise ValueError(
                "protected root generation must be positive"
            )
        claims = tuple(self.claims)
        object.__setattr__(
            self,
            "claims",
            claims,
        )
        if any(
            claim.chain_id != self.chain_id
            or claim.root_hash != self.root_hash
            for claim in claims
        ):
            raise ValueError(
                "root protection claim binding mismatch"
            )
        claim_ids = tuple(
            claim.claim_id
            for claim in claims
        )
        if len(claim_ids) != len(
            set(claim_ids)
        ):
            raise ValueError(
                "duplicate root protection claim"
            )
        if claim_ids != tuple(
            sorted(claim_ids)
        ):
            raise ValueError(
                "root protection claims must be sorted"
            )
        object.__setattr__(
            self,
            "updated_at",
            _timestamp(
                "updated_at",
                self.updated_at,
            ),
        )

    def active_claims(
        self,
        now: float,
    ) -> tuple[DurableRootProtectionClaim, ...]:
        now = _timestamp("now", now)
        return tuple(
            claim
            for claim in self.claims
            if claim.active(now)
        )

    def expired_claims(
        self,
        now: float,
    ) -> tuple[DurableRootProtectionClaim, ...]:
        now = _timestamp("now", now)
        return tuple(
            claim
            for claim in self.claims
            if not claim.active(now)
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "root_hash": self.root_hash,
            "generation": self.generation,
            "claims": [
                claim.to_dict()
                for claim in self.claims
            ],
            "updated_at": self.updated_at,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class StoredDurableProtectedRoot:
    revision: int
    protected_root: DurableProtectedRoot

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "protected root revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "protected_root": (
                self.protected_root.to_dict()
            ),
        }


@dataclass(frozen=True)
class DurableRootProtectionReport:
    chain_id: str
    root_hash: str
    revision: int | None
    generation: int
    claims: tuple[DurableRootProtectionClaim, ...]
    active_claims: tuple[DurableRootProtectionClaim, ...]
    expired_claims: tuple[DurableRootProtectionClaim, ...]
    inspected_at: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        if self.revision is not None and (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "protection revision must be positive when present"
            )
        if (
            isinstance(self.generation, bool)
            or not isinstance(
                self.generation,
                int,
            )
            or self.generation < 0
        ):
            raise ValueError(
                "protection generation must be non-negative"
            )
        object.__setattr__(
            self,
            "claims",
            tuple(self.claims),
        )
        object.__setattr__(
            self,
            "active_claims",
            tuple(self.active_claims),
        )
        object.__setattr__(
            self,
            "expired_claims",
            tuple(self.expired_claims),
        )
        object.__setattr__(
            self,
            "inspected_at",
            _timestamp(
                "inspected_at",
                self.inspected_at,
            ),
        )
        known = {
            item.claim_id
            for item in self.claims
        }
        if not {
            item.claim_id
            for item in self.active_claims
        }.issubset(known):
            raise ValueError(
                "active claims must belong to report claims"
            )
        if not {
            item.claim_id
            for item in self.expired_claims
        }.issubset(known):
            raise ValueError(
                "expired claims must belong to report claims"
            )

    @property
    def protected(self) -> bool:
        return bool(self.active_claims)

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def active_count(self) -> int:
        return len(self.active_claims)

    @property
    def expired_count(self) -> int:
        return len(self.expired_claims)

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "root_hash": self.root_hash,
            "revision": self.revision,
            "generation": self.generation,
            "claims": [
                claim.to_dict()
                for claim in self.claims
            ],
            "active_claims": [
                claim.to_dict()
                for claim in self.active_claims
            ],
            "expired_claims": [
                claim.to_dict()
                for claim in self.expired_claims
            ],
            "claim_count": self.claim_count,
            "active_count": self.active_count,
            "expired_count": self.expired_count,
            "protected": self.protected,
            "inspected_at": self.inspected_at,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableFinalizationRootProtections:
    finalization_id: str
    journal_claim: DurableRootProtectionClaim
    receipt_claim: DurableRootProtectionClaim

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                maximum=256,
            ),
        )
        if (
            self.journal_claim.source_id
            != self.finalization_id
            or self.receipt_claim.source_id
            != self.finalization_id
        ):
            raise ValueError(
                "finalization root claim source mismatch"
            )
        if (
            self.journal_claim.kind
            is not DurableRootProtectionKind.FINALIZATION
            or self.receipt_claim.kind
            is not DurableRootProtectionKind.FINALIZATION
        ):
            raise ValueError(
                "finalization root protections require finalization claims"
            )
        if (
            self.journal_claim.chain_id
            == self.receipt_claim.chain_id
        ):
            raise ValueError(
                "journal and receipt protection chain ids must differ"
            )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "finalization_id": self.finalization_id,
            "journal_claim": (
                self.journal_claim.to_dict()
            ),
            "receipt_claim": (
                self.receipt_claim.to_dict()
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableRootProtectionError(RuntimeError):
    pass


class DurableRootProtectionConflict(
    DurableRootProtectionError
):
    pass


class DurableRootProtected(
    DurableRootProtectionError
):
    pass


class DurableRootProtectionStore:
    """CAS-updated complete claim set for each protected historical root."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-root-protection",
        max_claims_per_root: int = 256,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid root protection namespace"
            )
        if (
            isinstance(max_claims_per_root, bool)
            or not isinstance(
                max_claims_per_root,
                int,
            )
            or max_claims_per_root <= 0
        ):
            raise ValueError(
                "max_claims_per_root must be positive integer"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.max_claims_per_root = (
            max_claims_per_root
        )
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _key(
        chain_id: str,
        root_hash: str,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        return (
            "root:"
            + hashlib.sha256(
                chain_id.encode()
            ).hexdigest()
            + ":"
            + root_hash
        )

    def _now(self) -> float:
        return _timestamp(
            "root protection clock",
            self._clock(),
        )

    def current(
        self,
        chain_id: str,
        root_hash: str,
    ) -> StoredDurableProtectedRoot | None:
        record = self.backend.get(
            self.namespace,
            self._key(
                chain_id,
                root_hash,
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableProtectedRoot,
        ):
            raise DurableRootProtectionConflict(
                "protected root record has invalid value type"
            )
        protected = record.value
        if (
            protected.chain_id != chain_id
            or protected.root_hash
            != root_hash.lower()
        ):
            raise DurableRootProtectionConflict(
                "protected root record identity mismatch"
            )
        return StoredDurableProtectedRoot(
            record.revision,
            protected,
        )

    @staticmethod
    def build_claim(
        *,
        chain_id: str,
        root_hash: str,
        kind: DurableRootProtectionKind,
        source_id: str,
        source_digest: str,
        created_at: float,
        expires_at: float = 0.0,
        reason: str = "",
    ) -> DurableRootProtectionClaim:
        claim_id = (
            DurableRootProtectionClaim.derive_id(
                chain_id=chain_id,
                root_hash=root_hash,
                kind=kind,
                source_id=source_id,
                source_digest=source_digest,
            )
        )
        return DurableRootProtectionClaim(
            1,
            claim_id,
            chain_id,
            root_hash,
            kind,
            source_id,
            source_digest,
            created_at,
            expires_at,
            reason,
        )

    def protect(
        self,
        *,
        chain_id: str,
        root_hash: str,
        kind: DurableRootProtectionKind,
        source_id: str,
        source_digest: str,
        expires_at: float = 0.0,
        reason: str = "",
    ) -> DurableRootProtectionClaim:
        now = self._now()
        claim = self.build_claim(
            chain_id=chain_id,
            root_hash=root_hash,
            kind=kind,
            source_id=source_id,
            source_digest=source_digest,
            created_at=now,
            expires_at=expires_at,
            reason=reason,
        )
        key = self._key(
            claim.chain_id,
            claim.root_hash,
        )

        for _ in range(
            self.max_cas_retries
        ):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                protected = DurableProtectedRoot(
                    1,
                    claim.chain_id,
                    claim.root_hash,
                    1,
                    (claim,),
                    now,
                )
                try:
                    self.backend.put_if_absent(
                        self.namespace,
                        key,
                        protected,
                    )
                    return claim
                except DistributedStateConflict:
                    continue

            if not isinstance(
                record.value,
                DurableProtectedRoot,
            ):
                raise DurableRootProtectionConflict(
                    "protected root record has invalid value type"
                )
            current = record.value
            if (
                current.chain_id
                != claim.chain_id
                or current.root_hash
                != claim.root_hash
            ):
                raise DurableRootProtectionConflict(
                    "protected root identity changed"
                )
            existing = tuple(
                item
                for item in current.claims
                if item.claim_id
                == claim.claim_id
            )
            if existing:
                if existing[0].source_digest != claim.source_digest:
                    raise DurableRootProtectionConflict(
                        "claim identity binds different source digest"
                    )
                return existing[0]
            if (
                len(current.claims)
                >= self.max_claims_per_root
            ):
                raise DurableRootProtectionConflict(
                    "protected root claim capacity exhausted"
                )
            claims = tuple(
                sorted(
                    current.claims + (claim,),
                    key=lambda item: item.claim_id,
                )
            )
            updated = DurableProtectedRoot(
                1,
                current.chain_id,
                current.root_hash,
                current.generation + 1,
                claims,
                now,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=(
                        record.revision
                    ),
                    value=updated,
                )
                return claim
            except DistributedStateConflict:
                continue
        raise DurableRootProtectionConflict(
            "root protection CAS retry budget exhausted"
        )

    def inspect(
        self,
        chain_id: str,
        root_hash: str,
        *,
        now: float | None = None,
    ) -> DurableRootProtectionReport:
        instant = (
            self._now()
            if now is None
            else _timestamp("now", now)
        )
        stored = self.current(
            chain_id,
            root_hash,
        )
        if stored is None:
            return DurableRootProtectionReport(
                chain_id,
                root_hash,
                None,
                0,
                (),
                (),
                (),
                instant,
            )
        protected = stored.protected_root
        return DurableRootProtectionReport(
            protected.chain_id,
            protected.root_hash,
            stored.revision,
            protected.generation,
            protected.claims,
            protected.active_claims(
                instant
            ),
            protected.expired_claims(
                instant
            ),
            instant,
        )

    def is_protected(
        self,
        chain_id: str,
        root_hash: str,
        *,
        now: float | None = None,
    ) -> bool:
        return self.inspect(
            chain_id,
            root_hash,
            now=now,
        ).protected

    def require_unprotected(
        self,
        chain_id: str,
        root_hash: str,
        *,
        now: float | None = None,
    ) -> DurableRootProtectionReport:
        report = self.inspect(
            chain_id,
            root_hash,
            now=now,
        )
        if report.protected:
            sources = ",".join(
                claim.source_id
                for claim in report.active_claims[
                    :8
                ]
            )
            raise DurableRootProtected(
                "historical root is protected"
                + (
                    f" by {sources}"
                    if sources
                    else ""
                )
            )
        return report

    def release(
        self,
        chain_id: str,
        root_hash: str,
        claim_id: str,
        *,
        expected_claim_digest: str = "",
    ) -> DurableRootProtectionReport:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        claim_id = _digest(
            "claim_id",
            claim_id,
        )
        expected_claim_digest = _digest(
            "expected_claim_digest",
            expected_claim_digest,
            optional=True,
        )
        key = self._key(
            chain_id,
            root_hash,
        )

        for _ in range(
            self.max_cas_retries
        ):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                return self.inspect(
                    chain_id,
                    root_hash,
                )
            if not isinstance(
                record.value,
                DurableProtectedRoot,
            ):
                raise DurableRootProtectionConflict(
                    "protected root record has invalid value type"
                )
            current = record.value
            matches = tuple(
                claim
                for claim in current.claims
                if claim.claim_id == claim_id
            )
            if not matches:
                return self.inspect(
                    chain_id,
                    root_hash,
                )
            claim = matches[0]
            if (
                expected_claim_digest
                and claim.digest
                != expected_claim_digest
            ):
                raise DurableRootProtectionConflict(
                    "root protection claim digest changed"
                )
            remaining = tuple(
                item
                for item in current.claims
                if item.claim_id != claim_id
            )
            updated = DurableProtectedRoot(
                1,
                current.chain_id,
                current.root_hash,
                current.generation + 1,
                remaining,
                self._now(),
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=(
                        record.revision
                    ),
                    value=updated,
                )
                return self.inspect(
                    chain_id,
                    root_hash,
                )
            except DistributedStateConflict:
                continue
        raise DurableRootProtectionConflict(
            "root protection release CAS retry budget exhausted"
        )

    def purge_expired(
        self,
        chain_id: str,
        root_hash: str,
        *,
        now: float | None = None,
    ) -> DurableRootProtectionReport:
        instant = (
            self._now()
            if now is None
            else _timestamp("now", now)
        )
        key = self._key(
            chain_id,
            root_hash,
        )
        for _ in range(
            self.max_cas_retries
        ):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                return self.inspect(
                    chain_id,
                    root_hash,
                    now=instant,
                )
            if not isinstance(
                record.value,
                DurableProtectedRoot,
            ):
                raise DurableRootProtectionConflict(
                    "protected root record has invalid value type"
                )
            current = record.value
            remaining = tuple(
                claim
                for claim in current.claims
                if claim.active(instant)
            )
            if remaining == current.claims:
                return self.inspect(
                    chain_id,
                    root_hash,
                    now=instant,
                )
            updated = DurableProtectedRoot(
                1,
                current.chain_id,
                current.root_hash,
                current.generation + 1,
                remaining,
                instant,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=updated,
                )
                return self.inspect(
                    chain_id,
                    root_hash,
                    now=instant,
                )
            except DistributedStateConflict:
                continue
        raise DurableRootProtectionConflict(
            "root protection expiry purge CAS retry budget exhausted"
        )

    def protect_finalization(
        self,
        *,
        finalization_id: str,
        source_digest: str,
        journal_chain_id: str,
        journal_root: str,
        receipt_chain_id: str,
        receipt_root: str,
    ) -> DurableFinalizationRootProtections:
        if journal_chain_id == receipt_chain_id:
            raise ValueError(
                "journal and receipt chain ids must differ"
            )
        journal_claim = self.protect(
            chain_id=journal_chain_id,
            root_hash=journal_root,
            kind=(
                DurableRootProtectionKind.FINALIZATION
            ),
            source_id=finalization_id,
            source_digest=source_digest,
            reason=(
                "journal root retained by finalized "
                "AI execution"
            ),
        )
        receipt_claim = self.protect(
            chain_id=receipt_chain_id,
            root_hash=receipt_root,
            kind=(
                DurableRootProtectionKind.FINALIZATION
            ),
            source_id=finalization_id,
            source_digest=source_digest,
            reason=(
                "receipt root retained by finalized "
                "AI execution"
            ),
        )
        return DurableFinalizationRootProtections(
            finalization_id,
            journal_claim,
            receipt_claim,
        )
