"""Signed, replay-safe failover authorization for durable evidence replicas.

A replica being in sync is a point-in-time fact. This module turns that fact
into a short-lived signed ticket, persists a globally unique claim, and checks
the live replication roots again immediately before the promotion is marked
applied. A source advance between claim and completion therefore makes the
ticket stale rather than silently promoting an out-of-date replica.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import secrets
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceOperation,
    DurableMaintenanceResource,
    DurableMaintenanceStale,
    DurableMaintenanceStore,
    SignedDurableMaintenanceEpoch,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetError,
)
from skeleton.shells.ai.durable_replication import (
    DurableEvidenceReplicaManager,
    DurableEvidenceReplicationReport,
    DurableReplicationError,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


FAILOVER_ARTIFACT_TYPE = "shell-ai-durable-failover-ticket"


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        ) from exc
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    max_length: int = 128,
) -> str:
    if not value or len(value) > max_length:
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class DurableFailoverTicket:
    schema_version: int
    ticket_id: str
    source_id: str
    target_id: str
    issued_at: float
    expires_at: float
    nonce: str
    replication_report_digest: str
    policy_digest: str
    journal_sequence: int
    journal_root: str
    receipt_sequence: int
    receipt_root: str
    fleet_state_digest: str = ""
    fleet_policy_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable failover ticket schema"
            )
        object.__setattr__(
            self,
            "ticket_id",
            _digest("ticket_id", self.ticket_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _identity("source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "target_id",
            _identity("target_id", self.target_id),
        )
        if self.source_id == self.target_id:
            raise ValueError(
                "failover source_id and target_id must differ"
            )
        for name in ("issued_at", "expires_at"):
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
                "failover ticket expiry must follow issue time"
            )
        if not self.nonce or len(self.nonce) > 128:
            raise ValueError("invalid failover ticket nonce")
        object.__setattr__(
            self,
            "replication_report_digest",
            _digest(
                "replication_report_digest",
                self.replication_report_digest,
            ),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest(
                "policy_digest",
                self.policy_digest,
            ),
        )
        for name in (
            "journal_sequence",
            "receipt_sequence",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        object.__setattr__(
            self,
            "journal_root",
            _digest(
                "journal_root",
                self.journal_root,
            ),
        )
        object.__setattr__(
            self,
            "receipt_root",
            _digest(
                "receipt_root",
                self.receipt_root,
            ),
        )
        object.__setattr__(
            self,
            "fleet_state_digest",
            _digest(
                "fleet_state_digest",
                self.fleet_state_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "fleet_policy_digest",
            _digest(
                "fleet_policy_digest",
                self.fleet_policy_digest,
                optional=True,
            ),
        )
        if bool(self.fleet_state_digest) != bool(
            self.fleet_policy_digest
        ):
            raise ValueError(
                "fleet failover digests must be configured together"
            )

    @staticmethod
    def derive_id(
        *,
        source_id: str,
        target_id: str,
        issued_at: float,
        expires_at: float,
        nonce: str,
        replication_report_digest: str,
        journal_root: str,
        receipt_root: str,
        fleet_state_digest: str = "",
        fleet_policy_digest: str = "",
    ) -> str:
        raw = json.dumps(
            {
                "source_id": source_id,
                "target_id": target_id,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "nonce": nonce,
                "replication_report_digest": (
                    replication_report_digest
                ),
                "journal_root": journal_root,
                "receipt_root": receipt_root,
                "fleet_state_digest": fleet_state_digest,
                "fleet_policy_digest": fleet_policy_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ticket_id": self.ticket_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "replication_report_digest": (
                self.replication_report_digest
            ),
            "policy_digest": self.policy_digest,
            "journal_sequence": self.journal_sequence,
            "journal_root": self.journal_root,
            "receipt_sequence": self.receipt_sequence,
            "receipt_root": self.receipt_root,
            "fleet_state_digest": self.fleet_state_digest,
            "fleet_policy_digest": self.fleet_policy_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignedDurableFailoverTicket:
    ticket: DurableFailoverTicket
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if self.signature.artifact_type != FAILOVER_ARTIFACT_TYPE:
            raise ValueError(
                "invalid failover signature artifact type"
            )
        if (
            self.signature.artifact_digest
            != self.ticket.digest
        ):
            raise ValueError(
                "failover signature does not bind ticket digest"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "ticket": self.ticket.to_dict(),
            "ticket_digest": self.ticket.digest,
            "signature": self.signature.to_dict(),
        }


class DurableFailoverTicketError(RuntimeError):
    pass


class DurableFailoverAuthority:
    """Issue and verify short-lived tickets bound to live replica roots."""

    def __init__(
        self,
        signer: ArtifactSigner,
        *,
        max_ttl_seconds: float = 300.0,
        max_clock_skew_seconds: float = 5.0,
        clock: Callable[[], float] = time.time,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(signer, ArtifactSigner):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        for name, value in (
            ("max_ttl_seconds", max_ttl_seconds),
            (
                "max_clock_skew_seconds",
                max_clock_skew_seconds,
            ),
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
        if not callable(clock):
            raise TypeError("clock must be callable")
        if nonce_factory is not None and not callable(
            nonce_factory
        ):
            raise TypeError(
                "nonce_factory must be callable"
            )
        self.signer = signer
        self.max_ttl_seconds = float(
            max_ttl_seconds
        )
        self.max_clock_skew_seconds = float(
            max_clock_skew_seconds
        )
        self._clock = clock
        self._nonce_factory = (
            nonce_factory
            or (lambda: secrets.token_hex(16))
        )

    @staticmethod
    def _promotion_roots(
        report: DurableEvidenceReplicationReport,
    ) -> tuple[int, str, int, str]:
        if not report.promotion_ready:
            raise DurableFailoverTicketError(
                "replication report is not promotion ready"
            )
        if (
            report.journal.source_sequence
            != report.journal.target_sequence
            or report.journal.source_root
            != report.journal.target_root
        ):
            raise DurableFailoverTicketError(
                "journal source/target heads differ"
            )
        if (
            report.receipts.source_sequence
            != report.receipts.target_sequence
            or report.receipts.source_root
            != report.receipts.target_root
        ):
            raise DurableFailoverTicketError(
                "receipt source/target heads differ"
            )
        return (
            report.journal.source_sequence,
            report.journal.source_root,
            report.receipts.source_sequence,
            report.receipts.source_root,
        )

    def issue(
        self,
        manager: DurableEvidenceReplicaManager,
        *,
        source_id: str,
        target_id: str,
        ttl_seconds: float = 60.0,
        fleet_state_digest: str = "",
        fleet_policy_digest: str = "",
    ) -> SignedDurableFailoverTicket:
        if not isinstance(
            manager,
            DurableEvidenceReplicaManager,
        ):
            raise TypeError(
                "manager must be DurableEvidenceReplicaManager"
            )
        source_id = _identity(
            "source_id",
            source_id,
        )
        target_id = _identity(
            "target_id",
            target_id,
        )
        if source_id == target_id:
            raise ValueError(
                "failover source_id and target_id must differ"
            )
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or not math.isfinite(float(ttl_seconds))
            or float(ttl_seconds) <= 0.0
            or float(ttl_seconds)
            > self.max_ttl_seconds
        ):
            raise ValueError(
                "ttl_seconds outside supported range"
            )
        if bool(fleet_state_digest) != bool(
            fleet_policy_digest
        ):
            raise ValueError(
                "fleet_state_digest and fleet_policy_digest must be paired"
            )
        fleet_state_digest = _digest(
            "fleet_state_digest",
            fleet_state_digest,
            optional=True,
        )
        fleet_policy_digest = _digest(
            "fleet_policy_digest",
            fleet_policy_digest,
            optional=True,
        )
        report = manager.require_promotion_ready()
        (
            journal_sequence,
            journal_root,
            receipt_sequence,
            receipt_root,
        ) = self._promotion_roots(report)
        now = float(self._clock())
        if not math.isfinite(now) or now < 0.0:
            raise DurableFailoverTicketError(
                "failover clock returned invalid time"
            )
        expires_at = now + float(ttl_seconds)
        nonce = str(self._nonce_factory())
        if not nonce or len(nonce) > 128:
            raise DurableFailoverTicketError(
                "nonce factory returned invalid value"
            )
        ticket_id = DurableFailoverTicket.derive_id(
            source_id=source_id,
            target_id=target_id,
            issued_at=now,
            expires_at=expires_at,
            nonce=nonce,
            replication_report_digest=report.digest,
            journal_root=journal_root,
            receipt_root=receipt_root,
            fleet_state_digest=fleet_state_digest,
            fleet_policy_digest=fleet_policy_digest,
        )
        ticket = DurableFailoverTicket(
            1,
            ticket_id,
            source_id,
            target_id,
            now,
            expires_at,
            nonce,
            report.digest,
            report.policy_digest,
            journal_sequence,
            journal_root,
            receipt_sequence,
            receipt_root,
            fleet_state_digest,
            fleet_policy_digest,
        )
        signature = self.signer.sign(
            FAILOVER_ARTIFACT_TYPE,
            ticket.digest,
            metadata={
                "ticket_id": ticket.ticket_id,
                "source_id": source_id,
                "target_id": target_id,
                "expires_at": repr(expires_at),
            },
        )
        return SignedDurableFailoverTicket(
            ticket,
            signature,
        )

    def verify_static(
        self,
        signed: SignedDurableFailoverTicket,
        *,
        source_id: str = "",
        target_id: str = "",
        enforce_time: bool = True,
    ) -> DurableFailoverTicket:
        """Verify signature, identity, metadata, and optionally ticket time."""
        if not isinstance(
            signed,
            SignedDurableFailoverTicket,
        ):
            raise TypeError(
                "signed must be SignedDurableFailoverTicket"
            )
        if not isinstance(enforce_time, bool):
            raise ValueError("enforce_time must be bool")
        try:
            self.signer.verify(
                signed.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableFailoverTicketError(
                "failover ticket signature verification failed"
            ) from exc

        ticket = signed.ticket
        if source_id and ticket.source_id != source_id:
            raise DurableFailoverTicketError(
                "failover ticket source_id mismatch"
            )
        if target_id and ticket.target_id != target_id:
            raise DurableFailoverTicketError(
                "failover ticket target_id mismatch"
            )
        metadata = signed.signature.metadata
        if (
            metadata.get("ticket_id")
            != ticket.ticket_id
            or metadata.get("source_id")
            != ticket.source_id
            or metadata.get("target_id")
            != ticket.target_id
            or metadata.get("expires_at")
            != repr(ticket.expires_at)
        ):
            raise DurableFailoverTicketError(
                "failover ticket signed metadata mismatch"
            )

        if enforce_time:
            now = float(self._clock())
            if not math.isfinite(now) or now < 0.0:
                raise DurableFailoverTicketError(
                    "failover clock returned invalid time"
                )
            if (
                ticket.issued_at
                > now + self.max_clock_skew_seconds
            ):
                raise DurableFailoverTicketError(
                    "failover ticket issue time is too far in the future"
                )
            if now > ticket.expires_at:
                raise DurableFailoverTicketError(
                    "failover ticket expired"
                )
            if (
                ticket.expires_at - ticket.issued_at
                > self.max_ttl_seconds
            ):
                raise DurableFailoverTicketError(
                    "failover ticket TTL exceeds authority maximum"
                )
            if (
                abs(
                    signed.signature.issued_at
                    - ticket.issued_at
                )
                > self.max_clock_skew_seconds
            ):
                raise DurableFailoverTicketError(
                    "failover signature/ticket issue times differ"
                )
        return ticket

    def verify(
        self,
        signed: SignedDurableFailoverTicket,
        manager: DurableEvidenceReplicaManager,
        *,
        source_id: str = "",
        target_id: str = "",
    ) -> DurableFailoverTicket:
        if not isinstance(
            manager,
            DurableEvidenceReplicaManager,
        ):
            raise TypeError(
                "manager must be DurableEvidenceReplicaManager"
            )
        ticket = self.verify_static(
            signed,
            source_id=source_id,
            target_id=target_id,
            enforce_time=True,
        )

        try:
            report = manager.require_promotion_ready()
        except DurableReplicationError as exc:
            raise DurableFailoverTicketError(
                "replica is no longer promotion ready"
            ) from exc
        (
            journal_sequence,
            journal_root,
            receipt_sequence,
            receipt_root,
        ) = self._promotion_roots(report)
        if report.digest != ticket.replication_report_digest:
            raise DurableFailoverTicketError(
                "live replication report differs from failover ticket"
            )
        if report.policy_digest != ticket.policy_digest:
            raise DurableFailoverTicketError(
                "replication policy differs from failover ticket"
            )
        if (
            journal_sequence
            != ticket.journal_sequence
            or journal_root != ticket.journal_root
        ):
            raise DurableFailoverTicketError(
                "live journal head differs from failover ticket"
            )
        if (
            receipt_sequence
            != ticket.receipt_sequence
            or receipt_root != ticket.receipt_root
        ):
            raise DurableFailoverTicketError(
                "live receipt head differs from failover ticket"
            )
        return ticket


class DurableFailoverPhase(str, Enum):
    CLAIMED = "claimed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DurableFailoverRecord:
    schema_version: int
    claim_id: str
    ticket_id: str
    ticket_digest: str
    source_id: str
    target_id: str
    consumer_id: str
    phase: DurableFailoverPhase
    claimed_at: float
    updated_at: float
    applied_report_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported failover record schema"
            )
        object.__setattr__(
            self,
            "claim_id",
            _digest("claim_id", self.claim_id),
        )
        object.__setattr__(
            self,
            "ticket_id",
            _digest("ticket_id", self.ticket_id),
        )
        object.__setattr__(
            self,
            "ticket_digest",
            _digest(
                "ticket_digest",
                self.ticket_digest,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _identity("source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "target_id",
            _identity("target_id", self.target_id),
        )
        object.__setattr__(
            self,
            "consumer_id",
            _identity(
                "consumer_id",
                self.consumer_id,
                max_length=160,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            DurableFailoverPhase(self.phase),
        )
        for name in (
            "claimed_at",
            "updated_at",
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
        if self.updated_at < self.claimed_at:
            raise ValueError(
                "failover updated_at precedes claim"
            )
        object.__setattr__(
            self,
            "applied_report_digest",
            _digest(
                "applied_report_digest",
                self.applied_report_digest,
                optional=True,
            ),
        )
        if (
            self.phase is DurableFailoverPhase.APPLIED
            and not self.applied_report_digest
        ):
            raise ValueError(
                "applied failover requires report digest"
            )
        if (
            self.phase is not DurableFailoverPhase.APPLIED
            and self.applied_report_digest
        ):
            raise ValueError(
                "non-applied failover may not bind applied report"
            )

    @staticmethod
    def derive_claim_id(
        ticket_id: str,
        consumer_id: str,
    ) -> str:
        raw = json.dumps(
            {
                "ticket_id": ticket_id,
                "consumer_id": consumer_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def terminal(self) -> bool:
        return self.phase in {
            DurableFailoverPhase.APPLIED,
            DurableFailoverPhase.CANCELLED,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "ticket_id": self.ticket_id,
            "ticket_digest": self.ticket_digest,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "consumer_id": self.consumer_id,
            "phase": self.phase.value,
            "claimed_at": self.claimed_at,
            "updated_at": self.updated_at,
            "applied_report_digest": (
                self.applied_report_digest
            ),
            "terminal": self.terminal,
        }


@dataclass(frozen=True)
class StoredDurableFailover:
    revision: int
    record: DurableFailoverRecord

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "failover revision must be positive integer"
            )


class DurableFailoverConflict(RuntimeError):
    pass


class DurableFailoverRegistry:
    """Globally serialize promotion claims by signed ticket identity."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-durable-failover",
        max_cas_retries: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid durable failover namespace"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 64
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _key(ticket_id: str) -> str:
        ticket_id = _digest(
            "ticket_id",
            ticket_id,
        )
        return "ticket:" + hashlib.sha256(
            ticket_id.encode()
        ).hexdigest()

    def current(
        self,
        ticket_id: str,
    ) -> StoredDurableFailover | None:
        record = self.backend.get(
            self.namespace,
            self._key(ticket_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableFailoverRecord,
        ):
            raise RuntimeError(
                "failover registry value type mismatch"
            )
        return StoredDurableFailover(
            record.revision,
            record.value,
        )

    def claim(
        self,
        ticket: DurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> StoredDurableFailover:
        if not isinstance(
            ticket,
            DurableFailoverTicket,
        ):
            raise TypeError(
                "ticket must be DurableFailoverTicket"
            )
        consumer_id = _identity(
            "consumer_id",
            consumer_id,
            max_length=160,
        )
        now = float(self._clock())
        if not math.isfinite(now) or now < 0.0:
            raise DurableFailoverConflict(
                "failover registry clock returned invalid time"
            )
        claim_id = (
            DurableFailoverRecord
            .derive_claim_id(
                ticket.ticket_id,
                consumer_id,
            )
        )
        item = DurableFailoverRecord(
            1,
            claim_id,
            ticket.ticket_id,
            ticket.digest,
            ticket.source_id,
            ticket.target_id,
            consumer_id,
            DurableFailoverPhase.CLAIMED,
            now,
            now,
        )
        key = self._key(
            ticket.ticket_id
        )
        try:
            stored = self.backend.put_if_absent(
                self.namespace,
                key,
                item,
            )
            return StoredDurableFailover(
                stored.revision,
                item,
            )
        except DistributedStateConflict as exc:
            current = self.current(
                ticket.ticket_id
            )
            if current is None:
                raise
            if (
                current.record.ticket_digest
                != ticket.digest
            ):
                raise DurableFailoverConflict(
                    "ticket_id already binds a different failover ticket"
                ) from exc
            if (
                current.record.consumer_id
                != consumer_id
            ):
                raise DurableFailoverConflict(
                    "failover ticket is already claimed by another consumer"
                ) from exc
            return current

    def _transition(
        self,
        ticket: DurableFailoverTicket,
        *,
        consumer_id: str,
        phase: DurableFailoverPhase,
        applied_report_digest: str = "",
    ) -> StoredDurableFailover:
        consumer_id = _identity(
            "consumer_id",
            consumer_id,
            max_length=160,
        )
        phase = DurableFailoverPhase(phase)
        if phase not in {
            DurableFailoverPhase.APPLIED,
            DurableFailoverPhase.CANCELLED,
        }:
            raise ValueError(
                "unsupported failover terminal transition"
            )
        for _ in range(self.max_cas_retries):
            current = self.current(
                ticket.ticket_id
            )
            if current is None:
                raise DurableFailoverConflict(
                    "failover ticket is not claimed"
                )
            item = current.record
            if item.ticket_digest != ticket.digest:
                raise DurableFailoverConflict(
                    "claimed failover ticket digest mismatch"
                )
            if item.consumer_id != consumer_id:
                raise DurableFailoverConflict(
                    "failover claim owner mismatch"
                )
            if item.phase is phase:
                if (
                    phase is DurableFailoverPhase.APPLIED
                    and item.applied_report_digest
                    != applied_report_digest
                ):
                    raise DurableFailoverConflict(
                        "applied failover report digest mismatch"
                    )
                return current
            if item.terminal:
                raise DurableFailoverConflict(
                    "failover claim is already terminal"
                )
            now = float(self._clock())
            updated = replace(
                item,
                phase=phase,
                updated_at=now,
                applied_report_digest=(
                    applied_report_digest
                    if phase
                    is DurableFailoverPhase.APPLIED
                    else ""
                ),
            )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    self._key(ticket.ticket_id),
                    expected_revision=current.revision,
                    value=updated,
                )
                return StoredDurableFailover(
                    stored.revision,
                    updated,
                )
            except DistributedStateConflict:
                continue
        raise DurableFailoverConflict(
            "failover transition CAS retry budget exhausted"
        )

    def applied(
        self,
        ticket: DurableFailoverTicket,
        *,
        consumer_id: str,
        replication_report_digest: str,
    ) -> StoredDurableFailover:
        return self._transition(
            ticket,
            consumer_id=consumer_id,
            phase=DurableFailoverPhase.APPLIED,
            applied_report_digest=_digest(
                "replication_report_digest",
                replication_report_digest,
            ),
        )

    def cancel(
        self,
        ticket: DurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> StoredDurableFailover:
        return self._transition(
            ticket,
            consumer_id=consumer_id,
            phase=DurableFailoverPhase.CANCELLED,
        )


class DurableFailoverCoordinator:
    """Issue, claim, and complete failover with live root revalidation."""

    def __init__(
        self,
        manager: DurableEvidenceReplicaManager,
        authority: DurableFailoverAuthority,
        registry: DurableFailoverRegistry,
        *,
        source_id: str,
        target_id: str,
        fleet: DurableReplicaFleet | None = None,
        maintenance: DurableMaintenanceStore | None = None,
    ) -> None:
        if not isinstance(
            manager,
            DurableEvidenceReplicaManager,
        ):
            raise TypeError(
                "manager must be DurableEvidenceReplicaManager"
            )
        if not isinstance(
            authority,
            DurableFailoverAuthority,
        ):
            raise TypeError(
                "authority must be DurableFailoverAuthority"
            )
        if not isinstance(
            registry,
            DurableFailoverRegistry,
        ):
            raise TypeError(
                "registry must be DurableFailoverRegistry"
            )
        self.manager = manager
        self.authority = authority
        self.registry = registry
        self.source_id = _identity(
            "source_id",
            source_id,
        )
        self.target_id = _identity(
            "target_id",
            target_id,
        )
        if self.source_id == self.target_id:
            raise ValueError(
                "failover source_id and target_id must differ"
            )
        if fleet is not None and not isinstance(
            fleet,
            DurableReplicaFleet,
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleet"
            )
        if (
            fleet is not None
            and fleet.source_id != self.source_id
        ):
            raise ValueError(
                "failover fleet source_id mismatch"
            )
        if (
            maintenance is not None
            and not isinstance(
                maintenance,
                DurableMaintenanceStore,
            )
        ):
            raise TypeError(
                "maintenance must be DurableMaintenanceStore"
            )
        self.fleet = fleet
        self.maintenance = maintenance

    def _maintenance_resources(
        self,
        report: DurableEvidenceReplicationReport,
    ) -> tuple[
        DurableMaintenanceResource,
        DurableMaintenanceResource,
    ]:
        journal_id = self.manager.journal.chain_id
        receipt_id = self.manager.receipts.chain_id
        if journal_id == receipt_id:
            raise DurableFailoverTicketError(
                "failover journal and receipt chain ids must differ"
            )
        journal = (
            DurableMaintenanceResource
            .replicated_chain(
                journal_id,
                source_sequence=(
                    report.journal.source_sequence
                ),
                source_root=(
                    report.journal.source_root
                ),
                target_sequence=(
                    report.journal.target_sequence
                ),
                target_root=(
                    report.journal.target_root
                ),
                replication_state_digest=(
                    report.digest
                ),
            )
        )
        receipts = (
            DurableMaintenanceResource
            .replicated_chain(
                receipt_id,
                source_sequence=(
                    report.receipts.source_sequence
                ),
                source_root=(
                    report.receipts.source_root
                ),
                target_sequence=(
                    report.receipts.target_sequence
                ),
                target_root=(
                    report.receipts.target_root
                ),
                replication_state_digest=(
                    report.digest
                ),
            )
        )
        return tuple(
            sorted(
                (journal, receipts),
                key=lambda item: item.resource_id,
            )
        )

    def maintenance_resources(
        self,
    ) -> tuple[
        DurableMaintenanceResource,
        DurableMaintenanceResource,
    ]:
        return self._maintenance_resources(
            self.manager.require_promotion_ready()
        )

    def _require_maintenance(
        self,
        report: DurableEvidenceReplicationReport,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ),
    ):
        if self.maintenance is None:
            return None
        if maintenance_epoch is None:
            raise DurableFailoverTicketError(
                "durable maintenance epoch is required for failover"
            )
        if not isinstance(
            maintenance_epoch,
            SignedDurableMaintenanceEpoch,
        ):
            raise TypeError(
                "maintenance_epoch must be SignedDurableMaintenanceEpoch"
            )
        resources = self._maintenance_resources(
            report
        )
        try:
            return self.maintenance.require_active(
                maintenance_epoch,
                operation=(
                    DurableMaintenanceOperation.FAILOVER
                ),
                required_resources=tuple(
                    item.resource_id
                    for item in resources
                ),
                live_resources=resources,
            )
        except DurableMaintenanceStale as exc:
            raise DurableFailoverTicketError(
                "durable maintenance authority is stale: "
                + str(exc)
            ) from exc

    def _fleet_report(self):
        if self.fleet is None:
            return None
        try:
            return self.fleet.require_quorum(
                target_id=self.target_id
            )
        except DurableReplicaFleetError as exc:
            raise DurableFailoverTicketError(
                "replica fleet quorum is not ready"
            ) from exc

    def _require_ticket_fleet(
        self,
        ticket: DurableFailoverTicket,
    ):
        report = self._fleet_report()
        if report is None:
            if (
                ticket.fleet_state_digest
                or ticket.fleet_policy_digest
            ):
                raise DurableFailoverTicketError(
                    "failover ticket requires unavailable fleet verification"
                )
            return None
        if (
            not ticket.fleet_state_digest
            or not ticket.fleet_policy_digest
        ):
            raise DurableFailoverTicketError(
                "fleet failover ticket lacks fleet commitments"
            )
        if (
            ticket.fleet_state_digest
            != report.state_digest
        ):
            raise DurableFailoverTicketError(
                "live replica fleet state differs from failover ticket"
            )
        if (
            ticket.fleet_policy_digest
            != report.policy_digest
        ):
            raise DurableFailoverTicketError(
                "live replica fleet policy differs from failover ticket"
            )
        return report

    def issue(
        self,
        *,
        ttl_seconds: float = 60.0,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ) = None,
    ) -> SignedDurableFailoverTicket:
        fleet_report = self._fleet_report()
        if self.maintenance is not None:
            report = self.manager.require_promotion_ready()
            self._require_maintenance(
                report,
                maintenance_epoch,
            )
        return self.authority.issue(
            self.manager,
            source_id=self.source_id,
            target_id=self.target_id,
            ttl_seconds=ttl_seconds,
            fleet_state_digest=(
                ""
                if fleet_report is None
                else fleet_report.state_digest
            ),
            fleet_policy_digest=(
                ""
                if fleet_report is None
                else fleet_report.policy_digest
            ),
        )

    def claim(
        self,
        signed: SignedDurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> StoredDurableFailover:
        ticket = self.authority.verify(
            signed,
            self.manager,
            source_id=self.source_id,
            target_id=self.target_id,
        )
        self._require_ticket_fleet(ticket)
        return self.registry.claim(
            ticket,
            consumer_id=consumer_id,
        )

    def complete(
        self,
        signed: SignedDurableFailoverTicket,
        *,
        consumer_id: str,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ) = None,
    ) -> StoredDurableFailover:
        current = self.registry.current(
            signed.ticket.ticket_id
        )
        if (
            current is not None
            and current.record.phase
            is DurableFailoverPhase.APPLIED
        ):
            ticket = self.authority.verify_static(
                signed,
                source_id=self.source_id,
                target_id=self.target_id,
                enforce_time=False,
            )
            if (
                current.record.consumer_id
                != consumer_id
            ):
                raise DurableFailoverConflict(
                    "applied failover owner mismatch"
                )
            if (
                current.record.ticket_digest
                != ticket.digest
            ):
                raise DurableFailoverConflict(
                    "applied failover ticket digest mismatch"
                )
            return current

        ticket = self.authority.verify(
            signed,
            self.manager,
            source_id=self.source_id,
            target_id=self.target_id,
        )
        self._require_ticket_fleet(ticket)
        report = self.manager.require_promotion_ready()
        self._require_maintenance(
            report,
            maintenance_epoch,
        )
        return self.registry.applied(
            ticket,
            consumer_id=consumer_id,
            replication_report_digest=report.digest,
        )

    def cancel(
        self,
        signed: SignedDurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> StoredDurableFailover:
        ticket = self.authority.verify_static(
            signed,
            source_id=self.source_id,
            target_id=self.target_id,
            enforce_time=False,
        )
        return self.registry.cancel(
            ticket,
            consumer_id=consumer_id,
        )
