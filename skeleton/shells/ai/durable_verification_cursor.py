"""Signed incremental verification cursors for durable evidence chains.

A cursor is a signed statement that a chain prefix was fully verified at a
specific sequence/root. Later verification can validate only the bounded tail
from that trusted root to a stable current head. Policy periodically forces a
full replay so retained historical bytes are re-audited instead of being
trusted forever.

This is a verification accelerator, not a replacement for signed evidence,
archive authority, recovery requirements, or destructive-compaction gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Protocol, runtime_checkable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be a 64-character digest")
    return value.lower()


def _chain_id(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > 128:
        raise ValueError("invalid chain_id")
    return value


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _segment_digest(items: tuple[object, ...]) -> str:
    encoded: list[object] = []
    for item in items:
        to_dict = getattr(item, "to_dict", None)
        encoded.append(
            to_dict()
            if callable(to_dict)
            else repr(item)
        )
    return _stable_digest(encoded)


@runtime_checkable
class IncrementallyVerifiableChain(Protocol):
    def head(self): ...
    def verify(self) -> bool: ...
    def snapshot_segment(
        self,
        start_exclusive_root: str,
        end_inclusive_root: str = "",
        *,
        max_items: int = 4096,
    ) -> tuple[object, ...]: ...


class DurableVerificationMode(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class DurableVerificationStatus(str, Enum):
    NO_CURSOR = "no_cursor"
    CURRENT = "current"
    TAIL_PENDING = "tail_pending"
    TAIL_VERIFIED = "tail_verified"
    FULL_VERIFIED = "full_verified"
    FULL_REQUIRED = "full_required"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableVerificationPolicy:
    max_tail_items: int = 4096
    max_items_between_full_verification: int = 50_000
    max_full_verification_age_seconds: float = 3600.0
    max_head_retries: int = 4
    allow_full_bootstrap: bool = True
    allow_full_refresh: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_tail_items",
            "max_items_between_full_verification",
            "max_head_retries",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a positive integer")
        if self.max_tail_items > self.max_items_between_full_verification:
            raise ValueError(
                "max_tail_items may not exceed "
                "max_items_between_full_verification"
            )
        age = self.max_full_verification_age_seconds
        if (
            isinstance(age, bool)
            or not isinstance(age, (int, float))
            or not math.isfinite(float(age))
            or float(age) <= 0.0
        ):
            raise ValueError(
                "max_full_verification_age_seconds must be finite and positive"
            )
        object.__setattr__(
            self,
            "max_full_verification_age_seconds",
            float(age),
        )
        for name in (
            "allow_full_bootstrap",
            "allow_full_refresh",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "max_tail_items": self.max_tail_items,
            "max_items_between_full_verification": (
                self.max_items_between_full_verification
            ),
            "max_full_verification_age_seconds": (
                self.max_full_verification_age_seconds
            ),
            "max_head_retries": self.max_head_retries,
            "allow_full_bootstrap": self.allow_full_bootstrap,
            "allow_full_refresh": self.allow_full_refresh,
        }


@dataclass(frozen=True)
class DurableVerificationCursor:
    schema_version: int
    chain_id: str
    sequence: int
    root_hash: str
    previous_cursor_digest: str
    mode: DurableVerificationMode
    verified_at: float
    last_full_verified_at: float
    full_verified_sequence: int
    segment_start_root: str
    segment_items: int
    segment_digest: str
    policy_digest: str
    verifier_version: str = "1"

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported durable verification cursor schema")
        object.__setattr__(self, "chain_id", _chain_id(self.chain_id))
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("cursor sequence must be non-negative")
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        object.__setattr__(
            self,
            "previous_cursor_digest",
            _digest(
                "previous_cursor_digest",
                self.previous_cursor_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "mode",
            DurableVerificationMode(self.mode),
        )
        for name in (
            "verified_at",
            "last_full_verified_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, float(value))
        if self.last_full_verified_at > self.verified_at:
            raise ValueError(
                "last_full_verified_at may not be after verified_at"
            )
        if (
            isinstance(self.full_verified_sequence, bool)
            or not isinstance(self.full_verified_sequence, int)
            or self.full_verified_sequence < 0
            or self.full_verified_sequence > self.sequence
        ):
            raise ValueError("invalid full_verified_sequence")
        object.__setattr__(
            self,
            "segment_start_root",
            _digest(
                "segment_start_root",
                self.segment_start_root,
            ),
        )
        if (
            isinstance(self.segment_items, bool)
            or not isinstance(self.segment_items, int)
            or self.segment_items < 0
        ):
            raise ValueError("segment_items must be non-negative")
        object.__setattr__(
            self,
            "segment_digest",
            _digest("segment_digest", self.segment_digest),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest("policy_digest", self.policy_digest),
        )
        if not self.verifier_version or len(self.verifier_version) > 64:
            raise ValueError("invalid verifier_version")
        if self.mode is DurableVerificationMode.FULL:
            if self.full_verified_sequence != self.sequence:
                raise ValueError(
                    "full cursor must full-verify its own sequence"
                )
            if self.last_full_verified_at != self.verified_at:
                raise ValueError(
                    "full cursor timestamps must match"
                )
        if self.mode is DurableVerificationMode.INCREMENTAL:
            if not self.previous_cursor_digest:
                raise ValueError(
                    "incremental cursor requires previous_cursor_digest"
                )
            if self.segment_items <= 0:
                raise ValueError(
                    "incremental cursor requires a non-empty segment"
                )

    @property
    def verified_item_count(self) -> int:
        """Backward-compatible alias for the verified segment size."""
        return self.segment_items

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "previous_cursor_digest": self.previous_cursor_digest,
            "mode": self.mode.value,
            "verified_at": self.verified_at,
            "last_full_verified_at": self.last_full_verified_at,
            "full_verified_sequence": self.full_verified_sequence,
            "segment_start_root": self.segment_start_root,
            "segment_items": self.segment_items,
            "segment_digest": self.segment_digest,
            "policy_digest": self.policy_digest,
            "verifier_version": self.verifier_version,
        }


@dataclass(frozen=True)
class SignedDurableVerificationCursor:
    cursor: DurableVerificationCursor
    signature: SignedArtifact

    def to_dict(self) -> dict[str, object]:
        return {
            "cursor": self.cursor.to_dict(),
            "cursor_digest": self.cursor.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableVerificationCursorHead:
    chain_id: str
    cursor_digest: str
    sequence: int
    root_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chain_id", _chain_id(self.chain_id))
        object.__setattr__(
            self,
            "cursor_digest",
            _digest("cursor_digest", self.cursor_digest),
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("cursor head sequence must be non-negative")
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "cursor_digest": self.cursor_digest,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
        }


@dataclass(frozen=True)
class StoredDurableVerificationCursor:
    head_revision: int
    item: SignedDurableVerificationCursor

    def __post_init__(self) -> None:
        if (
            isinstance(self.head_revision, bool)
            or not isinstance(self.head_revision, int)
            or self.head_revision <= 0
        ):
            raise ValueError("head_revision must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "head_revision": self.head_revision,
            "item": self.item.to_dict(),
        }


@dataclass(frozen=True)
class DurableVerificationReport:
    chain_id: str
    status: DurableVerificationStatus
    current_sequence: int
    current_root: str
    cursor_sequence: int | None
    cursor_root: str
    cursor_digest: str
    tail_items: int
    full_age_seconds: float | None
    items_since_full: int | None
    head_retries: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "chain_id", _chain_id(self.chain_id))
        object.__setattr__(
            self,
            "status",
            DurableVerificationStatus(self.status),
        )
        if (
            isinstance(self.current_sequence, bool)
            or not isinstance(self.current_sequence, int)
            or self.current_sequence < 0
        ):
            raise ValueError("current_sequence must be non-negative")
        object.__setattr__(
            self,
            "current_root",
            _digest("current_root", self.current_root),
        )
        if self.cursor_sequence is not None and (
            isinstance(self.cursor_sequence, bool)
            or not isinstance(self.cursor_sequence, int)
            or self.cursor_sequence < 0
        ):
            raise ValueError("cursor_sequence must be non-negative")
        object.__setattr__(
            self,
            "cursor_root",
            _digest("cursor_root", self.cursor_root, optional=True),
        )
        object.__setattr__(
            self,
            "cursor_digest",
            _digest("cursor_digest", self.cursor_digest, optional=True),
        )
        if (
            isinstance(self.tail_items, bool)
            or not isinstance(self.tail_items, int)
            or self.tail_items < 0
        ):
            raise ValueError("tail_items must be non-negative")
        if self.full_age_seconds is not None and (
            isinstance(self.full_age_seconds, bool)
            or not isinstance(self.full_age_seconds, (int, float))
            or not math.isfinite(float(self.full_age_seconds))
            or float(self.full_age_seconds) < 0.0
        ):
            raise ValueError("full_age_seconds must be non-negative")
        if self.items_since_full is not None and (
            isinstance(self.items_since_full, bool)
            or not isinstance(self.items_since_full, int)
            or self.items_since_full < 0
        ):
            raise ValueError("items_since_full must be non-negative")
        if (
            isinstance(self.head_retries, bool)
            or not isinstance(self.head_retries, int)
            or self.head_retries < 0
        ):
            raise ValueError("head_retries must be non-negative")
        object.__setattr__(self, "reasons", tuple(self.reasons))

    @property
    def unverified_tail_items(self) -> int:
        """Backward-compatible name for the pending tail size."""
        return self.tail_items

    @property
    def valid(self) -> bool:
        return self.status in {
            DurableVerificationStatus.CURRENT,
            DurableVerificationStatus.TAIL_VERIFIED,
            DurableVerificationStatus.FULL_VERIFIED,
        }

    @property
    def full_required(self) -> bool:
        return self.status in {
            DurableVerificationStatus.NO_CURSOR,
            DurableVerificationStatus.FULL_REQUIRED,
        }

    @property
    def verified_item_count(self) -> int:
        """Backward-compatible name for the verified segment size."""
        return self.segment_items

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_dict(include_digest=False))

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "status": self.status.value,
            "valid": self.valid,
            "full_required": self.full_required,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cursor_sequence": self.cursor_sequence,
            "cursor_root": self.cursor_root,
            "cursor_digest": self.cursor_digest,
            "tail_items": self.tail_items,
            "full_age_seconds": self.full_age_seconds,
            "items_since_full": self.items_since_full,
            "head_retries": self.head_retries,
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableVerificationResult:
    report: DurableVerificationReport
    cursor: SignedDurableVerificationCursor | None
    published: bool

    @property
    def item(self) -> SignedDurableVerificationCursor | None:
        """Backward-compatible alias for the published/current cursor."""
        return self.cursor

    @property
    def valid(self) -> bool:
        return self.report.valid

    def to_dict(self) -> dict[str, object]:
        return {
            "report": self.report.to_dict(),
            "cursor": (
                None
                if self.cursor is None
                else self.cursor.to_dict()
            ),
            "published": self.published,
            "valid": self.valid,
        }


class DurableVerificationCursorError(RuntimeError):
    pass


class DurableVerificationCursorStore:
    """CAS-backed immutable cursor records with one movable head per chain."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-verification-cursors",
        max_cas_retries: int = 16,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid verification cursor namespace")
        if not isinstance(signer, ArtifactSigner):
            raise TypeError("signer must be ArtifactSigner")
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 64
        ):
            raise ValueError("max_cas_retries outside supported range")
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries

    @staticmethod
    def _cursor_key(cursor_digest: str) -> str:
        return "cursor:" + _digest("cursor_digest", cursor_digest)

    @staticmethod
    def _head_key(chain_id: str) -> str:
        chain_id = _chain_id(chain_id)
        return "head:" + hashlib.sha256(chain_id.encode()).hexdigest()

    def sign(
        self,
        cursor: DurableVerificationCursor,
    ) -> SignedDurableVerificationCursor:
        if not isinstance(cursor, DurableVerificationCursor):
            raise TypeError("cursor must be DurableVerificationCursor")
        signature = self.signer.sign(
            "durable-verification-cursor",
            cursor.digest,
            metadata={
                "chain_id": cursor.chain_id,
                "sequence": str(cursor.sequence),
                "mode": cursor.mode.value,
                "policy_digest": cursor.policy_digest,
            },
        )
        return SignedDurableVerificationCursor(
            cursor,
            signature,
        )

    def verify_item(
        self,
        item: SignedDurableVerificationCursor,
    ) -> None:
        if not isinstance(item, SignedDurableVerificationCursor):
            raise TypeError(
                "item must be SignedDurableVerificationCursor"
            )
        if (
            item.signature.artifact_type
            != "durable-verification-cursor"
        ):
            raise DurableVerificationCursorError(
                "verification cursor artifact type mismatch"
            )
        if (
            item.signature.artifact_digest
            != item.cursor.digest
        ):
            raise DurableVerificationCursorError(
                "verification cursor signature digest mismatch"
            )
        metadata = dict(item.signature.metadata)
        expected = {
            "chain_id": item.cursor.chain_id,
            "sequence": str(item.cursor.sequence),
            "mode": item.cursor.mode.value,
            "policy_digest": item.cursor.policy_digest,
        }
        if metadata != expected:
            raise DurableVerificationCursorError(
                "verification cursor signature metadata mismatch"
            )
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise DurableVerificationCursorError(
                "verification cursor signature invalid"
            ) from exc

    def _put_immutable(
        self,
        item: SignedDurableVerificationCursor,
    ) -> None:
        self.verify_item(item)
        key = self._cursor_key(item.cursor.digest)
        existing = self.backend.get(self.namespace, key)
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    item,
                )
                return
            except DistributedStateConflict:
                existing = self.backend.get(self.namespace, key)
                if existing is None:
                    raise
        if not isinstance(
            existing.value,
            SignedDurableVerificationCursor,
        ):
            raise DurableVerificationCursorError(
                "verification cursor record type mismatch"
            )
        if existing.value != item:
            raise DurableVerificationCursorError(
                "verification cursor digest collision"
            )

    def get(
        self,
        cursor_digest: str,
    ) -> SignedDurableVerificationCursor | None:
        record = self.backend.get(
            self.namespace,
            self._cursor_key(cursor_digest),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableVerificationCursor,
        ):
            raise DurableVerificationCursorError(
                "verification cursor record type mismatch"
            )
        self.verify_item(record.value)
        return record.value

    def latest(
        self,
        chain_id: str,
    ) -> StoredDurableVerificationCursor | None:
        chain_id = _chain_id(chain_id)
        head_record = self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )
        if head_record is None:
            return None
        if not isinstance(
            head_record.value,
            DurableVerificationCursorHead,
        ):
            raise DurableVerificationCursorError(
                "verification cursor head type mismatch"
            )
        head = head_record.value
        if head.chain_id != chain_id:
            raise DurableVerificationCursorError(
                "verification cursor head chain mismatch"
            )
        item = self.get(head.cursor_digest)
        if item is None:
            raise DurableVerificationCursorError(
                "verification cursor head references missing cursor"
            )
        if (
            item.cursor.sequence != head.sequence
            or item.cursor.root_hash != head.root_hash
        ):
            raise DurableVerificationCursorError(
                "verification cursor head differs from signed cursor"
            )
        return StoredDurableVerificationCursor(
            head_record.revision,
            item,
        )

    def lineage(
        self,
        chain_id: str,
        *,
        max_items: int = 4096,
    ) -> tuple[SignedDurableVerificationCursor, ...]:
        """Return the signed cursor lineage from oldest to newest."""
        chain_id = _chain_id(chain_id)
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        latest = self.latest(chain_id)
        if latest is None:
            return ()

        reverse: list[
            SignedDurableVerificationCursor
        ] = []
        seen: set[str] = set()
        current = latest.item
        while True:
            digest = current.cursor.digest
            if digest in seen:
                raise DurableVerificationCursorError(
                    "verification cursor lineage contains a cycle"
                )
            seen.add(digest)
            reverse.append(current)
            if len(reverse) > max_items:
                raise DurableVerificationCursorError(
                    "verification cursor lineage exceeds bounded audit window"
                )
            previous_digest = (
                current.cursor.previous_cursor_digest
            )
            if not previous_digest:
                break
            previous = self.get(
                previous_digest
            )
            if previous is None:
                raise DurableVerificationCursorError(
                    "verification cursor lineage predecessor is missing"
                )
            if (
                previous.cursor.chain_id
                != chain_id
            ):
                raise DurableVerificationCursorError(
                    "verification cursor lineage crosses chain identity"
                )
            current = previous

        lineage = tuple(reversed(reverse))
        if not lineage:
            return ()
        if lineage[0].cursor.previous_cursor_digest:
            raise DurableVerificationCursorError(
                "verification cursor lineage does not begin at origin"
            )
        if (
            lineage[0].cursor.mode
            is not DurableVerificationMode.FULL
        ):
            raise DurableVerificationCursorError(
                "verification cursor lineage origin is not a full verification"
            )

        previous = lineage[0]
        for child in lineage[1:]:
            parent_cursor = previous.cursor
            child_cursor = child.cursor
            if (
                child_cursor.previous_cursor_digest
                != parent_cursor.digest
            ):
                raise DurableVerificationCursorError(
                    "verification cursor lineage digest link mismatch"
                )
            if (
                child_cursor.sequence
                < parent_cursor.sequence
            ):
                raise DurableVerificationCursorError(
                    "verification cursor lineage sequence regressed"
                )
            if (
                child_cursor.sequence
                == parent_cursor.sequence
                and child_cursor.root_hash
                != parent_cursor.root_hash
            ):
                raise DurableVerificationCursorError(
                    "verification cursor lineage forked at equal sequence"
                )
            if (
                child_cursor.mode
                is DurableVerificationMode.INCREMENTAL
            ):
                if (
                    child_cursor.sequence
                    <= parent_cursor.sequence
                ):
                    raise DurableVerificationCursorError(
                        "incremental cursor lineage must advance sequence"
                    )
                if (
                    child_cursor.segment_start_root
                    != parent_cursor.root_hash
                ):
                    raise DurableVerificationCursorError(
                        "incremental cursor lineage start root mismatch"
                    )
                expected_items = (
                    child_cursor.sequence
                    - parent_cursor.sequence
                )
                if (
                    child_cursor.segment_items
                    != expected_items
                ):
                    raise DurableVerificationCursorError(
                        "incremental cursor lineage segment count mismatch"
                    )
            previous = child

        head = latest.item.cursor
        if (
            lineage[-1].cursor.digest
            != head.digest
        ):
            raise DurableVerificationCursorError(
                "verification cursor lineage does not end at canonical head"
            )
        return lineage

    def verify_lineage(
        self,
        chain_id: str,
        *,
        max_items: int = 4096,
    ) -> bool:
        try:
            self.lineage(
                chain_id,
                max_items=max_items,
            )
        except (
            DurableVerificationCursorError,
            ValueError,
            TypeError,
        ):
            return False
        return True

    def publish(
        self,
        item: SignedDurableVerificationCursor,
    ) -> StoredDurableVerificationCursor:
        self.verify_item(item)
        self._put_immutable(item)
        chain_id = item.cursor.chain_id
        key = self._head_key(chain_id)

        for _ in range(self.max_cas_retries):
            current_record = self.backend.get(
                self.namespace,
                key,
            )
            if current_record is None:
                if item.cursor.previous_cursor_digest:
                    raise DurableVerificationCursorError(
                        "first verification cursor may not reference predecessor"
                    )
                head = DurableVerificationCursorHead(
                    chain_id,
                    item.cursor.digest,
                    item.cursor.sequence,
                    item.cursor.root_hash,
                )
                try:
                    stored = self.backend.put_if_absent(
                        self.namespace,
                        key,
                        head,
                    )
                    return StoredDurableVerificationCursor(
                        stored.revision,
                        item,
                    )
                except DistributedStateConflict:
                    continue

            if not isinstance(
                current_record.value,
                DurableVerificationCursorHead,
            ):
                raise DurableVerificationCursorError(
                    "verification cursor head type mismatch"
                )
            current = current_record.value
            if current.cursor_digest == item.cursor.digest:
                return StoredDurableVerificationCursor(
                    current_record.revision,
                    item,
                )
            if (
                item.cursor.previous_cursor_digest
                != current.cursor_digest
            ):
                raise DurableVerificationCursorError(
                    "verification cursor predecessor is stale"
                )
            if item.cursor.sequence < current.sequence:
                raise DurableVerificationCursorError(
                    "verification cursor sequence may not regress"
                )
            if (
                item.cursor.sequence == current.sequence
                and item.cursor.root_hash != current.root_hash
            ):
                raise DurableVerificationCursorError(
                    "verification cursor may not fork at equal sequence"
                )
            head = DurableVerificationCursorHead(
                chain_id,
                item.cursor.digest,
                item.cursor.sequence,
                item.cursor.root_hash,
            )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=current_record.revision,
                    value=head,
                )
                return StoredDurableVerificationCursor(
                    stored.revision,
                    item,
                )
            except DistributedStateConflict:
                continue

        raise DurableVerificationCursorError(
            "verification cursor head CAS retry budget exhausted"
        )


class DurableIncrementalVerifier:
    """Maintain a signed current verification point for one or more chains."""

    def __init__(
        self,
        store: DurableVerificationCursorStore,
        policy: DurableVerificationPolicy | None = None,
        *,
        clock: Callable[[], float] = time.time,
        verifier_version: str = "1",
    ) -> None:
        if not isinstance(store, DurableVerificationCursorStore):
            raise TypeError("store must be DurableVerificationCursorStore")
        self.store = store
        self.policy = policy or DurableVerificationPolicy()
        if not isinstance(self.policy, DurableVerificationPolicy):
            raise TypeError("policy must be DurableVerificationPolicy")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not verifier_version or len(verifier_version) > 64:
            raise ValueError("invalid verifier_version")
        self._clock = clock
        self.verifier_version = verifier_version

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise DurableVerificationCursorError(
                "verification clock returned invalid time"
            )
        return float(value)

    @staticmethod
    def _head(chain) -> tuple[int, str]:
        head = chain.head()
        sequence = int(head.sequence)
        root_hash = _digest(
            "chain root",
            str(head.root_hash),
        )
        if sequence < 0:
            raise DurableVerificationCursorError(
                "chain head sequence is negative"
            )
        return sequence, root_hash

    def inspect(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
    ) -> DurableVerificationReport:
        chain_id = _chain_id(chain_id)
        if not isinstance(chain, IncrementallyVerifiableChain):
            raise TypeError(
                "chain does not implement incremental verification protocol"
            )
        current_sequence, current_root = self._head(chain)
        # Validate the verifier clock on every inspection, including bootstrap
        # before the first cursor exists. A poisoned clock must never be hidden
        # by the NO_CURSOR fast path.
        now = self._now()
        latest = self.store.latest(chain_id)
        if latest is None:
            return DurableVerificationReport(
                chain_id,
                DurableVerificationStatus.NO_CURSOR,
                current_sequence,
                current_root,
                None,
                "",
                "",
                current_sequence,
                None,
                None,
                0,
                ("no signed verification cursor exists",),
            )

        cursor = latest.item.cursor
        reasons: list[str] = []
        if cursor.policy_digest != self.policy.digest:
            reasons.append(
                "cursor policy differs from active verification policy"
            )
        if cursor.verifier_version != self.verifier_version:
            reasons.append(
                "cursor verifier version differs from active verifier"
            )
        if current_sequence < cursor.sequence:
            reasons.append(
                "chain sequence regressed behind verification cursor"
            )
        if (
            current_sequence == cursor.sequence
            and current_root != cursor.root_hash
        ):
            reasons.append(
                "chain root forked at verification cursor sequence"
            )

        full_age = max(
            0.0,
            now - cursor.last_full_verified_at,
        )
        # A regressed chain is INVALID, but report construction itself must
        # remain total. Clamp presentation metrics while preserving the explicit
        # regression reason above.
        items_since_full = max(
            0,
            current_sequence - cursor.full_verified_sequence,
        )
        tail_items = max(
            0,
            current_sequence - cursor.sequence,
        )
        if reasons:
            status = DurableVerificationStatus.INVALID
        elif (
            full_age
            > self.policy.max_full_verification_age_seconds
        ):
            status = DurableVerificationStatus.FULL_REQUIRED
            reasons.append(
                "periodic full verification age exceeded"
            )
        elif (
            items_since_full
            > self.policy.max_items_between_full_verification
        ):
            status = DurableVerificationStatus.FULL_REQUIRED
            reasons.append(
                "items since full verification exceeded policy"
            )
        elif tail_items > self.policy.max_tail_items:
            status = DurableVerificationStatus.FULL_REQUIRED
            reasons.append(
                "unverified tail exceeds bounded incremental window"
            )
        elif tail_items == 0:
            status = DurableVerificationStatus.CURRENT
        else:
            status = DurableVerificationStatus.TAIL_PENDING

        return DurableVerificationReport(
            chain_id,
            status,
            current_sequence,
            current_root,
            cursor.sequence,
            cursor.root_hash,
            cursor.digest,
            tail_items,
            full_age,
            items_since_full,
            0,
            tuple(reasons),
        )

    def _full_cursor(
        self,
        chain_id: str,
        sequence: int,
        root_hash: str,
        *,
        previous_cursor_digest: str,
        now: float,
    ) -> DurableVerificationCursor:
        return DurableVerificationCursor(
            1,
            chain_id,
            sequence,
            root_hash,
            previous_cursor_digest,
            DurableVerificationMode.FULL,
            now,
            now,
            sequence,
            root_hash,
            sequence,
            _stable_digest(
                {
                    "mode": "full",
                    "sequence": sequence,
                    "root_hash": root_hash,
                }
            ),
            self.policy.digest,
            self.verifier_version,
        )

    def _incremental_cursor(
        self,
        chain_id: str,
        previous: DurableVerificationCursor,
        sequence: int,
        root_hash: str,
        segment: tuple[object, ...],
        *,
        now: float,
    ) -> DurableVerificationCursor:
        return DurableVerificationCursor(
            1,
            chain_id,
            sequence,
            root_hash,
            previous.digest,
            DurableVerificationMode.INCREMENTAL,
            now,
            previous.last_full_verified_at,
            previous.full_verified_sequence,
            previous.root_hash,
            len(segment),
            _segment_digest(segment),
            self.policy.digest,
            self.verifier_version,
        )

    def _publish_full(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
    ) -> DurableVerificationResult:
        previous = self.store.latest(chain_id)
        previous_digest = (
            ""
            if previous is None
            else previous.item.cursor.digest
        )
        for retry in range(self.policy.max_head_retries):
            before_sequence, before_root = self._head(chain)
            if not chain.verify():
                continue
            after_sequence, after_root = self._head(chain)
            if (
                before_sequence != after_sequence
                or before_root != after_root
            ):
                continue
            now = self._now()
            cursor = self._full_cursor(
                chain_id,
                after_sequence,
                after_root,
                previous_cursor_digest=previous_digest,
                now=now,
            )
            signed = self.store.sign(cursor)
            try:
                stored = self.store.publish(signed)
            except DurableVerificationCursorError as exc:
                refreshed = self.store.latest(chain_id)
                if (
                    refreshed is not None
                    and refreshed.item.cursor.sequence
                    >= after_sequence
                ):
                    return self.ensure_current(
                        chain_id,
                        chain,
                    )
                raise exc
            report = DurableVerificationReport(
                chain_id,
                DurableVerificationStatus.FULL_VERIFIED,
                after_sequence,
                after_root,
                cursor.sequence,
                cursor.root_hash,
                cursor.digest,
                0,
                0.0,
                0,
                retry,
                (),
            )
            return DurableVerificationResult(
                report,
                stored.item,
                True,
            )
        raise DurableVerificationCursorError(
            "could not full-verify a stable chain head"
        )

    def _bounded_tail_segment(
        self,
        chain: IncrementallyVerifiableChain,
        cursor: DurableVerificationCursor,
        sequence: int,
        root_hash: str,
    ) -> tuple[object, ...]:
        """Resolve a bounded verified tail, preferring sequence indexes.

        Sequence locators are accelerators only.  When a chain exposes the
        indexed range surface, both cursor and head roots must resolve to the
        exact signed/live roots before the hash-linked range is accepted.
        """
        snapshot_range = getattr(
            chain,
            "snapshot_range",
            None,
        )
        root_for_sequence = getattr(
            chain,
            "root_for_sequence",
            None,
        )
        if callable(snapshot_range) and callable(root_for_sequence):
            try:
                indexed_cursor_root = str(
                    root_for_sequence(
                        cursor.sequence
                    )
                )
                indexed_head_root = str(
                    root_for_sequence(
                        sequence
                    )
                )
            except Exception as exc:
                raise DurableVerificationCursorError(
                    "indexed tail root resolution failed"
                ) from exc
            if indexed_cursor_root != cursor.root_hash:
                raise DurableVerificationCursorError(
                    "sequence index disagrees with signed cursor root"
                )
            if indexed_head_root != root_hash:
                raise DurableVerificationCursorError(
                    "sequence index disagrees with live head root"
                )
            try:
                segment = snapshot_range(
                    cursor.sequence + 1,
                    sequence,
                    max_items=self.policy.max_tail_items,
                )
            except Exception as exc:
                raise DurableVerificationCursorError(
                    "indexed tail verification failed"
                ) from exc
        else:
            try:
                segment = chain.snapshot_segment(
                    cursor.root_hash,
                    root_hash,
                    max_items=self.policy.max_tail_items,
                )
            except Exception as exc:
                raise DurableVerificationCursorError(
                    "hash-linked tail verification failed"
                ) from exc

        expected = sequence - cursor.sequence
        if len(segment) != expected:
            raise DurableVerificationCursorError(
                "verified tail length differs from sequence delta"
            )
        if segment:
            first_sequence = getattr(
                segment[0],
                "sequence",
                None,
            )
            last_sequence = getattr(
                segment[-1],
                "sequence",
                None,
            )
            if (
                first_sequence != cursor.sequence + 1
                or last_sequence != sequence
            ):
                raise DurableVerificationCursorError(
                    "verified tail sequence bounds are inconsistent"
                )
            previous_hash = getattr(
                segment[0],
                "previous_hash",
                None,
            )
            if (
                previous_hash is not None
                and previous_hash != cursor.root_hash
            ):
                raise DurableVerificationCursorError(
                    "verified tail does not extend signed cursor root"
                )
            terminal_hash = getattr(
                segment[-1],
                "event_hash",
                getattr(
                    segment[-1],
                    "receipt_hash",
                    None,
                ),
            )
            if (
                terminal_hash is not None
                and terminal_hash != root_hash
            ):
                raise DurableVerificationCursorError(
                    "verified tail does not terminate at live head root"
                )
        return tuple(segment)

    def _publish_incremental(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
        previous: StoredDurableVerificationCursor,
    ) -> DurableVerificationResult:
        cursor = previous.item.cursor
        for retry in range(self.policy.max_head_retries):
            sequence, root_hash = self._head(chain)
            if sequence < cursor.sequence:
                raise DurableVerificationCursorError(
                    "chain regressed behind verification cursor"
                )
            if sequence == cursor.sequence:
                if root_hash != cursor.root_hash:
                    raise DurableVerificationCursorError(
                        "chain forked at verification cursor sequence"
                    )
                report = DurableVerificationReport(
                    chain_id,
                    DurableVerificationStatus.CURRENT,
                    sequence,
                    root_hash,
                    cursor.sequence,
                    cursor.root_hash,
                    cursor.digest,
                    0,
                    max(
                        0.0,
                        self._now() - cursor.last_full_verified_at,
                    ),
                    sequence - cursor.full_verified_sequence,
                    retry,
                    (),
                )
                return DurableVerificationResult(
                    report,
                    previous.item,
                    False,
                )
            delta = sequence - cursor.sequence
            if delta > self.policy.max_tail_items:
                raise DurableVerificationCursorError(
                    "incremental verification tail exceeds policy"
                )
            segment = self._bounded_tail_segment(
                chain,
                cursor,
                sequence,
                root_hash,
            )
            after_sequence, after_root = self._head(chain)
            if (
                after_sequence != sequence
                or after_root != root_hash
            ):
                continue
            now = self._now()
            next_cursor = self._incremental_cursor(
                chain_id,
                cursor,
                sequence,
                root_hash,
                segment,
                now=now,
            )
            signed = self.store.sign(next_cursor)
            try:
                stored = self.store.publish(signed)
            except DurableVerificationCursorError:
                refreshed = self.store.latest(chain_id)
                if refreshed is None:
                    raise
                if (
                    refreshed.item.cursor.sequence
                    >= sequence
                ):
                    return self.ensure_current(
                        chain_id,
                        chain,
                    )
                raise
            report = DurableVerificationReport(
                chain_id,
                DurableVerificationStatus.TAIL_VERIFIED,
                sequence,
                root_hash,
                next_cursor.sequence,
                next_cursor.root_hash,
                next_cursor.digest,
                len(segment),
                max(
                    0.0,
                    now - next_cursor.last_full_verified_at,
                ),
                sequence - next_cursor.full_verified_sequence,
                retry,
                (),
            )
            return DurableVerificationResult(
                report,
                stored.item,
                True,
            )
        raise DurableVerificationCursorError(
            "could not incrementally verify a stable chain head"
        )

    def ensure_current(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
    ) -> DurableVerificationResult:
        report = self.inspect(chain_id, chain)
        if report.status is DurableVerificationStatus.INVALID:
            raise DurableVerificationCursorError(
                "; ".join(report.reasons)
                or "verification cursor state is invalid"
            )
        if report.status is DurableVerificationStatus.NO_CURSOR:
            if not self.policy.allow_full_bootstrap:
                return DurableVerificationResult(
                    report,
                    None,
                    False,
                )
            return self._publish_full(
                chain_id,
                chain,
            )
        latest = self.store.latest(chain_id)
        if latest is None:
            raise DurableVerificationCursorError(
                "verification cursor disappeared during verification"
            )
        if report.status is DurableVerificationStatus.FULL_REQUIRED:
            if not self.policy.allow_full_refresh:
                return DurableVerificationResult(
                    report,
                    latest.item,
                    False,
                )
            return self._publish_full(
                chain_id,
                chain,
            )
        if report.status is DurableVerificationStatus.CURRENT:
            return DurableVerificationResult(
                report,
                latest.item,
                False,
            )
        if report.status is not DurableVerificationStatus.TAIL_PENDING:
            raise DurableVerificationCursorError(
                "unexpected verification cursor status: "
                f"{report.status.value}"
            )
        return self._publish_incremental(
            chain_id,
            chain,
            latest,
        )

    def full_verify(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
    ) -> DurableVerificationResult:
        """Explicitly perform and publish a stable full-chain verification."""
        chain_id = _chain_id(chain_id)
        if not isinstance(
            chain,
            IncrementallyVerifiableChain,
        ):
            raise TypeError(
                "chain does not implement incremental verification protocol"
            )
        return self._publish_full(
            chain_id,
            chain,
        )

    def require_current(
        self,
        chain_id: str,
        chain: IncrementallyVerifiableChain,
    ) -> DurableVerificationResult:
        result = self.ensure_current(
            chain_id,
            chain,
        )
        if not result.valid:
            raise DurableVerificationCursorError(
                "; ".join(result.report.reasons)
                or "durable chain is not currently verified"
            )
        return result
