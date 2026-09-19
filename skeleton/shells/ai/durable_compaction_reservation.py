"""Signed CAS reservations for exclusive durable compaction authority.

A cross-chain compaction group needs to prevent an unrelated single-chain
operator from certifying or executing one of its members while the group saga
is in progress.  Reservations are short-lived, signed, generation-ordered, and
stored behind one CAS head per chain.

The reservation is not pruning authority.  It only grants exclusive ownership
of the compaction control-plane lane for a chain.  Destructive authority still
requires the ordinary readiness certificate, pruning authorization, immutable
manifest, fencing lease, and hot-floor protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import secrets
import time
from typing import Callable, Iterable

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
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


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


@dataclass(frozen=True)
class DurableCompactionReservation:
    schema_version: int
    reservation_id: str
    chain_id: str
    holder_id: str
    operator_id: str
    generation: int
    nonce: str
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported compaction reservation schema"
            )
        object.__setattr__(
            self,
            "reservation_id",
            _digest(
                "reservation_id",
                self.reservation_id,
            ),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        _identity(
            "holder_id",
            self.holder_id,
            maximum=256,
        )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        _identity(
            "nonce",
            self.nonce,
            maximum=256,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "reservation generation must be positive"
            )
        for name in (
            "issued_at",
            "expires_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if self.expires_at <= self.issued_at:
            raise ValueError(
                "reservation expiry must follow issue time"
            )

    @classmethod
    def derive_id(
        cls,
        *,
        chain_id: str,
        holder_id: str,
        operator_id: str,
        generation: int,
        nonce: str,
        issued_at: float,
        expires_at: float,
    ) -> str:
        raw = json.dumps(
            {
                "chain_id": chain_id,
                "holder_id": holder_id,
                "operator_id": operator_id,
                "generation": generation,
                "nonce": nonce,
                "issued_at": float(issued_at),
                "expires_at": float(expires_at),
                "authority": (
                    "durable-compaction-reservation"
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def expired(
        self,
        now: float,
    ) -> bool:
        return float(now) >= self.expires_at

    def unsigned_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "reservation_id": self.reservation_id,
            "chain_id": self.chain_id,
            "holder_id": self.holder_id,
            "operator_id": self.operator_id,
            "generation": self.generation,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.unsigned_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            **self.unsigned_dict(),
            "digest": self.digest,
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class SignedDurableCompactionReservation:
    reservation: DurableCompactionReservation
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.reservation,
            DurableCompactionReservation,
        ):
            raise TypeError(
                "reservation must be DurableCompactionReservation"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    @property
    def reservation_id(self) -> str:
        return self.reservation.reservation_id

    @property
    def chain_id(self) -> str:
        return self.reservation.chain_id

    @property
    def holder_id(self) -> str:
        return self.reservation.holder_id

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "reservation": (
                self.reservation.to_dict()
            ),
            "signature": (
                self.signature.to_dict()
            ),
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class DurableCompactionReservationHead:
    chain_id: str
    reservation_id: str
    generation: int
    released_at: float = 0.0

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "reservation_id",
            _digest(
                "reservation_id",
                self.reservation_id,
            ),
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "reservation head generation must be positive"
            )
        if (
            isinstance(self.released_at, bool)
            or not isinstance(self.released_at, (int, float))
            or not math.isfinite(float(self.released_at))
            or float(self.released_at) < 0.0
        ):
            raise ValueError(
                "released_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "released_at",
            float(self.released_at),
        )

    @property
    def released(self) -> bool:
        return self.released_at > 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "reservation_id": self.reservation_id,
            "generation": self.generation,
            "released_at": self.released_at,
            "released": self.released,
        }


@dataclass(frozen=True)
class DurableCompactionReservationStatus:
    chain_id: str
    active: bool
    expired: bool
    released: bool
    holder_id: str
    operator_id: str
    reservation_id: str
    generation: int
    expires_at: float

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "active",
            "expired",
            "released",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if self.reservation_id:
            object.__setattr__(
                self,
                "reservation_id",
                _digest(
                    "reservation_id",
                    self.reservation_id,
                ),
            )
        if self.holder_id:
            _identity(
                "holder_id",
                self.holder_id,
                maximum=256,
            )
        if self.operator_id:
            _identity(
                "operator_id",
                self.operator_id,
                maximum=256,
            )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise ValueError(
                "reservation status generation must be non-negative"
            )
        if (
            isinstance(self.expires_at, bool)
            or not isinstance(self.expires_at, (int, float))
            or not math.isfinite(float(self.expires_at))
            or float(self.expires_at) < 0
        ):
            raise ValueError(
                "reservation status expires_at must be non-negative"
            )
        object.__setattr__(
            self,
            "expires_at",
            float(self.expires_at),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "active": self.active,
            "expired": self.expired,
            "released": self.released,
            "holder_id": self.holder_id,
            "operator_id": self.operator_id,
            "reservation_id": self.reservation_id,
            "generation": self.generation,
            "expires_at": self.expires_at,
        }


class DurableCompactionReservationError(RuntimeError):
    pass


class DurableCompactionReservationConflict(
    DurableCompactionReservationError
):
    pass


class DurableCompactionReservationStore:
    """Issue, verify, renew, and release exclusive per-chain reservations."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = (
            "shell-ai-durable-compaction-reservations"
        ),
        ttl_seconds: float = 600.0,
        max_ttl_seconds: float = 3600.0,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if (
            not namespace
            or len(namespace) > 128
        ):
            raise ValueError(
                "invalid compaction reservation namespace"
            )
        for name, value in (
            ("ttl_seconds", ttl_seconds),
            ("max_ttl_seconds", max_ttl_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and positive"
                )
        self.ttl_seconds = float(
            ttl_seconds
        )
        self.max_ttl_seconds = float(
            max_ttl_seconds
        )
        if (
            self.ttl_seconds
            > self.max_ttl_seconds
        ):
            raise ValueError(
                "ttl_seconds exceeds maximum"
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
        if (
            nonce_factory is not None
            and not callable(nonce_factory)
        ):
            raise TypeError(
                "nonce_factory must be callable"
            )
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries
        self._clock = clock
        self._nonce_factory = (
            nonce_factory
            or (
                lambda:
                secrets.token_hex(16)
            )
        )

    @staticmethod
    def _chain_hash(
        chain_id: str,
    ) -> str:
        _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        return hashlib.sha256(
            chain_id.encode()
        ).hexdigest()

    @classmethod
    def _head_key(
        cls,
        chain_id: str,
    ) -> str:
        return (
            "head:"
            + cls._chain_hash(chain_id)
        )

    @staticmethod
    def _item_key(
        reservation_id: str,
    ) -> str:
        return (
            "reservation:"
            + _digest(
                "reservation_id",
                reservation_id,
            )
        )

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise DurableCompactionReservationError(
                "reservation clock returned invalid time"
            )
        return float(value)

    def _head_record(
        self,
        chain_id: str,
    ):
        return self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )

    def _head(
        self,
        raw,
    ) -> DurableCompactionReservationHead:
        if not isinstance(
            raw,
            DurableCompactionReservationHead,
        ):
            raise DurableCompactionReservationError(
                "reservation head has invalid value type"
            )
        return raw

    def _verify_signature(
        self,
        item: SignedDurableCompactionReservation,
    ) -> None:
        try:
            payload = self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableCompactionReservationError(
                "reservation signature verification failed"
            ) from exc
        if payload != (
            item.reservation.unsigned_dict()
        ):
            raise DurableCompactionReservationError(
                "reservation signed payload differs from reservation"
            )
        metadata = (
            item.signature.metadata
        )
        if (
            metadata.get("authority")
            != "durable-compaction-reservation"
            or metadata.get("reservation_id")
            != item.reservation_id
            or metadata.get("chain_id")
            != item.chain_id
            or metadata.get("holder_id")
            != item.holder_id
        ):
            raise DurableCompactionReservationError(
                "reservation signature metadata mismatch"
            )

    def _signed(
        self,
        reservation: DurableCompactionReservation,
    ) -> SignedDurableCompactionReservation:
        signature = self.signer.sign(
            reservation.unsigned_dict(),
            metadata={
                "authority": (
                    "durable-compaction-reservation"
                ),
                "reservation_id": (
                    reservation.reservation_id
                ),
                "chain_id": reservation.chain_id,
                "holder_id": reservation.holder_id,
                "operator_id": (
                    reservation.operator_id
                ),
            },
        )
        return SignedDurableCompactionReservation(
            reservation,
            signature,
        )

    def _put_immutable(
        self,
        item: SignedDurableCompactionReservation,
    ) -> None:
        key = self._item_key(
            item.reservation_id
        )
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    item,
                )
                return
            except DistributedStateConflict:
                record = self.backend.get(
                    self.namespace,
                    key,
                )
                if record is None:
                    raise
        if not isinstance(
            record.value,
            SignedDurableCompactionReservation,
        ):
            raise DurableCompactionReservationError(
                "reservation item has invalid value type"
            )
        if record.value != item:
            raise DurableCompactionReservationError(
                "reservation id already binds different signed item"
            )

    def get(
        self,
        reservation_id: str,
    ) -> SignedDurableCompactionReservation | None:
        record = self.backend.get(
            self.namespace,
            self._item_key(
                reservation_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableCompactionReservation,
        ):
            raise DurableCompactionReservationError(
                "reservation item has invalid value type"
            )
        item = record.value
        self._verify_signature(item)
        if (
            item.reservation_id
            != reservation_id
        ):
            raise DurableCompactionReservationError(
                "reservation key/id mismatch"
            )
        return item

    def _current_raw(
        self,
        chain_id: str,
    ) -> tuple[
        int,
        DurableCompactionReservationHead,
        SignedDurableCompactionReservation,
    ] | None:
        record = self._head_record(
            chain_id
        )
        if record is None:
            return None
        head = self._head(
            record.value
        )
        if head.chain_id != chain_id:
            raise DurableCompactionReservationError(
                "reservation head chain mismatch"
            )
        item = self.get(
            head.reservation_id
        )
        if item is None:
            raise DurableCompactionReservationError(
                "reservation head references missing item"
            )
        if (
            item.chain_id != chain_id
            or item.reservation.generation
            != head.generation
        ):
            raise DurableCompactionReservationError(
                "reservation head/item binding mismatch"
            )
        return (
            record.revision,
            head,
            item,
        )

    def current(
        self,
        chain_id: str,
    ) -> SignedDurableCompactionReservation | None:
        current = self._current_raw(
            chain_id
        )
        if current is None:
            return None
        _, head, item = current
        if head.released:
            return None
        if item.reservation.expired(
            self._now()
        ):
            return None
        return item

    def status(
        self,
        chain_id: str,
    ) -> DurableCompactionReservationStatus:
        current = self._current_raw(
            chain_id
        )
        if current is None:
            return DurableCompactionReservationStatus(
                chain_id,
                False,
                False,
                False,
                "",
                "",
                "",
                0,
                0.0,
            )
        _, head, item = current
        now = self._now()
        expired = (
            item.reservation.expired(
                now
            )
        )
        active = (
            not head.released
            and not expired
        )
        return DurableCompactionReservationStatus(
            chain_id,
            active,
            expired,
            head.released,
            item.holder_id,
            item.reservation.operator_id,
            item.reservation_id,
            item.reservation.generation,
            item.reservation.expires_at,
        )

    def _ttl(
        self,
        value: float | None,
    ) -> float:
        ttl = (
            self.ttl_seconds
            if value is None
            else float(value)
        )
        if (
            not math.isfinite(ttl)
            or ttl <= 0.0
            or ttl > self.max_ttl_seconds
        ):
            raise ValueError(
                "reservation ttl outside supported range"
            )
        return ttl

    def _candidate(
        self,
        *,
        chain_id: str,
        holder_id: str,
        operator_id: str,
        generation: int,
        ttl_seconds: float,
    ) -> SignedDurableCompactionReservation:
        now = self._now()
        nonce = self._nonce_factory()
        _identity(
            "nonce",
            nonce,
            maximum=256,
        )
        expires_at = (
            now + ttl_seconds
        )
        reservation_id = (
            DurableCompactionReservation
            .derive_id(
                chain_id=chain_id,
                holder_id=holder_id,
                operator_id=operator_id,
                generation=generation,
                nonce=nonce,
                issued_at=now,
                expires_at=expires_at,
            )
        )
        return self._signed(
            DurableCompactionReservation(
                1,
                reservation_id,
                chain_id,
                holder_id,
                operator_id,
                generation,
                nonce,
                now,
                expires_at,
            )
        )

    def acquire(
        self,
        chain_id: str,
        *,
        holder_id: str,
        operator_id: str,
        ttl_seconds: float | None = None,
        force_renew: bool = False,
    ) -> SignedDurableCompactionReservation:
        _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        holder_id = _identity(
            "holder_id",
            holder_id,
            maximum=256,
        )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        ttl = self._ttl(
            ttl_seconds
        )
        if not isinstance(
            force_renew,
            bool,
        ):
            raise ValueError(
                "force_renew must be bool"
            )

        for _ in range(
            self.max_cas_retries
        ):
            record = self._head_record(
                chain_id
            )
            if record is None:
                revision = 0
                generation = 1
                previous = None
            else:
                revision = record.revision
                head = self._head(
                    record.value
                )
                previous = self.get(
                    head.reservation_id
                )
                if previous is None:
                    raise DurableCompactionReservationError(
                        "reservation head references missing item"
                    )
                now = self._now()
                previous_active = (
                    not head.released
                    and not previous.reservation.expired(
                        now
                    )
                )
                if previous_active:
                    if (
                        previous.holder_id
                        != holder_id
                        or previous.reservation.operator_id
                        != operator_id
                    ):
                        raise DurableCompactionReservationConflict(
                            "chain is reserved by another compaction holder"
                        )
                    if not force_renew:
                        return previous
                generation = (
                    head.generation + 1
                )

            candidate = self._candidate(
                chain_id=chain_id,
                holder_id=holder_id,
                operator_id=operator_id,
                generation=generation,
                ttl_seconds=ttl,
            )
            self._put_immutable(
                candidate
            )
            next_head = (
                DurableCompactionReservationHead(
                    chain_id,
                    candidate.reservation_id,
                    generation,
                    0.0,
                )
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    self._head_key(
                        chain_id
                    ),
                    expected_revision=revision,
                    value=next_head,
                )
                return candidate
            except DistributedStateConflict:
                continue
        raise DurableCompactionReservationError(
            "reservation CAS retry budget exhausted"
        )

    def renew(
        self,
        chain_id: str,
        *,
        holder_id: str,
        operator_id: str,
        ttl_seconds: float | None = None,
    ) -> SignedDurableCompactionReservation:
        current = self._current_raw(
            chain_id
        )
        if current is not None:
            _, head, item = current
            if (
                not head.released
                and not item.reservation.expired(
                    self._now()
                )
                and (
                    item.holder_id
                    != holder_id
                    or item.reservation.operator_id
                    != operator_id
                )
            ):
                raise DurableCompactionReservationConflict(
                    "cannot renew another holder's reservation"
                )
        return self.acquire(
            chain_id,
            holder_id=holder_id,
            operator_id=operator_id,
            ttl_seconds=ttl_seconds,
            force_renew=True,
        )

    def require_holder(
        self,
        chain_id: str,
        *,
        holder_id: str,
        operator_id: str = "",
    ) -> SignedDurableCompactionReservation:
        item = self.current(
            chain_id
        )
        if item is None:
            raise DurableCompactionReservationConflict(
                "chain has no active compaction reservation"
            )
        if item.holder_id != holder_id:
            raise DurableCompactionReservationConflict(
                "chain reservation belongs to a different holder"
            )
        if (
            operator_id
            and item.reservation.operator_id
            != operator_id
        ):
            raise DurableCompactionReservationConflict(
                "chain reservation operator differs from expected"
            )
        return item

    def assert_available(
        self,
        chain_id: str,
        *,
        holder_id: str = "",
    ) -> None:
        item = self.current(
            chain_id
        )
        if item is None:
            return
        if (
            holder_id
            and item.holder_id
            == holder_id
        ):
            return
        raise DurableCompactionReservationConflict(
            "chain is reserved by another compaction holder"
        )

    def release(
        self,
        chain_id: str,
        *,
        holder_id: str,
    ) -> DurableCompactionReservationHead:
        holder_id = _identity(
            "holder_id",
            holder_id,
            maximum=256,
        )
        for _ in range(
            self.max_cas_retries
        ):
            record = self._head_record(
                chain_id
            )
            if record is None:
                raise DurableCompactionReservationConflict(
                    "chain has no reservation to release"
                )
            head = self._head(
                record.value
            )
            item = self.get(
                head.reservation_id
            )
            if item is None:
                raise DurableCompactionReservationError(
                    "reservation head references missing item"
                )
            if item.holder_id != holder_id:
                raise DurableCompactionReservationConflict(
                    "cannot release another holder's reservation"
                )
            if head.released:
                return head
            released = (
                DurableCompactionReservationHead(
                    head.chain_id,
                    head.reservation_id,
                    head.generation,
                    self._now(),
                )
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    self._head_key(
                        chain_id
                    ),
                    expected_revision=record.revision,
                    value=released,
                )
                return released
            except DistributedStateConflict:
                continue
        raise DurableCompactionReservationError(
            "reservation release CAS retry budget exhausted"
        )

    def acquire_many(
        self,
        chain_ids: Iterable[str],
        *,
        holder_id: str,
        operator_id: str,
        ttl_seconds: float | None = None,
        renew: bool = False,
    ) -> tuple[
        SignedDurableCompactionReservation,
        ...,
    ]:
        ordered = tuple(
            sorted(chain_ids)
        )
        if (
            len(ordered) < 2
            or len(ordered)
            != len(set(ordered))
        ):
            raise ValueError(
                "reservation group requires unique chain ids"
            )
        acquired: list[
            SignedDurableCompactionReservation
        ] = []
        try:
            for chain_id in ordered:
                item = (
                    self.renew(
                        chain_id,
                        holder_id=holder_id,
                        operator_id=operator_id,
                        ttl_seconds=ttl_seconds,
                    )
                    if renew
                    else self.acquire(
                        chain_id,
                        holder_id=holder_id,
                        operator_id=operator_id,
                        ttl_seconds=ttl_seconds,
                    )
                )
                acquired.append(item)
        except Exception:
            for item in reversed(
                acquired
            ):
                try:
                    self.release(
                        item.chain_id,
                        holder_id=holder_id,
                    )
                except Exception:
                    pass
            raise
        return tuple(acquired)

    def release_many(
        self,
        chain_ids: Iterable[str],
        *,
        holder_id: str,
    ) -> tuple[
        DurableCompactionReservationHead,
        ...,
    ]:
        ordered = tuple(
            sorted(set(chain_ids))
        )
        return tuple(
            self.release(
                chain_id,
                holder_id=holder_id,
            )
            for chain_id in ordered
        )
