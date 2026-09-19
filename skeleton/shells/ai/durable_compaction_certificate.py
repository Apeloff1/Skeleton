"""Signed, expiring certificates for non-destructive compaction readiness.

A readiness certificate is audit evidence that a specific retention prefix was
covered by a verified archive at a specific live chain head. It is deliberately
not deletion authority. The signed metadata and object model both state that
the certificate is non-destructive, and current-use verification re-runs the
compaction planner to fence stale chain heads, archive drift, policy drift, and
protected-root drift.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_checkpoint import CheckpointableEvidenceChain
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionReadiness,
)
from skeleton.shells.ai.durable_retention import DurableRetentionPlan
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
        raise ValueError(
            f"{name} must be 64-character digest"
        )
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
class DurableCompactionCertificate:
    schema_version: int
    certificate_id: str
    chain_id: str
    readiness_digest: str
    retention_plan_digest: str
    compaction_policy_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    archive_id: str
    archive_manifest_digest: str
    protected_roots_digest: str
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported compaction certificate schema"
            )
        object.__setattr__(
            self,
            "certificate_id",
            _digest(
                "certificate_id",
                self.certificate_id,
            ),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "readiness_digest",
            "retention_plan_digest",
            "compaction_policy_digest",
            "current_root",
            "cutoff_root",
            "archive_manifest_digest",
            "protected_roots_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        for name in (
            "current_sequence",
            "cutoff_sequence",
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
        if self.cutoff_sequence <= 0:
            raise ValueError(
                "cutoff_sequence must be positive"
            )
        if (
            self.cutoff_sequence
            > self.current_sequence
        ):
            raise ValueError(
                "cutoff_sequence exceeds current_sequence"
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
                "certificate expiry must follow issue time"
            )

    @staticmethod
    def protected_digest(
        readiness: DurableCompactionReadiness,
    ) -> str:
        raw = json.dumps(
            [
                item.to_dict()
                for item in readiness.protected_roots
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def derive_id(
        cls,
        *,
        chain_id: str,
        readiness_digest: str,
        retention_plan_digest: str,
        compaction_policy_digest: str,
        current_sequence: int,
        current_root: str,
        cutoff_sequence: int,
        cutoff_root: str,
        archive_id: str,
        archive_manifest_digest: str,
        protected_roots_digest: str,
        issued_at: float,
        expires_at: float,
    ) -> str:
        payload = {
            "chain_id": chain_id,
            "readiness_digest": readiness_digest,
            "retention_plan_digest": retention_plan_digest,
            "compaction_policy_digest": compaction_policy_digest,
            "current_sequence": current_sequence,
            "current_root": current_root,
            "cutoff_sequence": cutoff_sequence,
            "cutoff_root": cutoff_root,
            "archive_id": archive_id,
            "archive_manifest_digest": (
                archive_manifest_digest
            ),
            "protected_roots_digest": (
                protected_roots_digest
            ),
            "issued_at": float(issued_at),
            "expires_at": float(expires_at),
            "authority": (
                "non-destructive-compaction-readiness"
            ),
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def unsigned_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "certificate_id": self.certificate_id,
            "chain_id": self.chain_id,
            "readiness_digest": self.readiness_digest,
            "retention_plan_digest": (
                self.retention_plan_digest
            ),
            "compaction_policy_digest": (
                self.compaction_policy_digest
            ),
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "protected_roots_digest": (
                self.protected_roots_digest
            ),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "destructive_action_authorized": False,
            "authority": (
                "non-destructive-compaction-readiness"
            ),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.unsigned_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class SignedDurableCompactionCertificate:
    certificate: DurableCompactionCertificate
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.certificate,
            DurableCompactionCertificate,
        ):
            raise TypeError(
                "certificate must be DurableCompactionCertificate"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    @property
    def certificate_id(self) -> str:
        return self.certificate.certificate_id

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "certificate": (
                self.certificate.to_dict()
            ),
            "signature": self.signature.to_dict(),
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class DurableCompactionCertificateHead:
    chain_id: str
    certificate_id: str
    current_sequence: int
    current_root: str
    issued_at: float

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "certificate_id",
            _digest(
                "certificate_id",
                self.certificate_id,
            ),
        )
        object.__setattr__(
            self,
            "current_root",
            _digest(
                "current_root",
                self.current_root,
            ),
        )
        if (
            isinstance(self.current_sequence, bool)
            or not isinstance(
                self.current_sequence,
                int,
            )
            or self.current_sequence < 0
        ):
            raise ValueError(
                "current_sequence must be non-negative"
            )
        if (
            isinstance(self.issued_at, bool)
            or not isinstance(
                self.issued_at,
                (int, float),
            )
            or not math.isfinite(
                float(self.issued_at)
            )
            or float(self.issued_at) < 0.0
        ):
            raise ValueError(
                "issued_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "issued_at",
            float(self.issued_at),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "certificate_id": self.certificate_id,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "issued_at": self.issued_at,
        }


@dataclass(frozen=True)
class DurableCompactionCertificateVerification:
    valid: bool
    current: bool
    expired: bool
    certificate_id: str
    chain_id: str
    readiness_digest: str
    current_readiness_digest: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "valid",
            "current",
            "expired",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "certificate_id",
            _digest(
                "certificate_id",
                self.certificate_id,
            ),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "readiness_digest",
            _digest(
                "readiness_digest",
                self.readiness_digest,
            ),
        )
        object.__setattr__(
            self,
            "current_readiness_digest",
            _digest(
                "current_readiness_digest",
                self.current_readiness_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def allowed(self) -> bool:
        return (
            self.valid
            and self.current
            and not self.expired
        )

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "current": self.current,
            "expired": self.expired,
            "allowed": self.allowed,
            "destructive_action_authorized": False,
            "certificate_id": self.certificate_id,
            "chain_id": self.chain_id,
            "readiness_digest": (
                self.readiness_digest
            ),
            "current_readiness_digest": (
                self.current_readiness_digest
            ),
            "reasons": list(self.reasons),
        }


class DurableCompactionCertificateError(
    RuntimeError
):
    pass


class DurableCompactionCertificateStore:
    """Issue and verify immutable non-destructive readiness certificates."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        planner: DurableCompactionPlanner,
        *,
        namespace: str = (
            "shell-ai-durable-compaction-certificates"
        ),
        ttl_seconds: float = 300.0,
        max_ttl_seconds: float = 3600.0,
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
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if not isinstance(
            planner,
            DurableCompactionPlanner,
        ):
            raise TypeError(
                "planner must be DurableCompactionPlanner"
            )
        if (
            not namespace
            or len(namespace) > 128
        ):
            raise ValueError(
                "invalid certificate namespace"
            )
        for name, value in (
            ("ttl_seconds", ttl_seconds),
            (
                "max_ttl_seconds",
                max_ttl_seconds,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
                or not math.isfinite(
                    float(value)
                )
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
            or not isinstance(
                max_cas_retries,
                int,
            )
            or not 1
            <= max_cas_retries
            <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self.backend = backend
        self.signer = signer
        self.planner = planner
        self.namespace = namespace
        self.max_cas_retries = (
            max_cas_retries
        )
        self._clock = clock

    @staticmethod
    def _certificate_key(
        certificate_id: str,
    ) -> str:
        return (
            "certificate:"
            + _digest(
                "certificate_id",
                certificate_id,
            )
        )

    @staticmethod
    def _head_key(
        chain_id: str,
    ) -> str:
        return (
            "head:"
            + hashlib.sha256(
                _identity(
                    "chain_id",
                    chain_id,
                    maximum=128,
                ).encode()
            ).hexdigest()
        )

    @staticmethod
    def _signature(
        raw: dict[str, object],
    ) -> SignedArtifact:
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            dict(
                raw.get(
                    "metadata",
                    {},
                )
            ),
            str(raw["signature"]),
        )

    @classmethod
    def _signed(
        cls,
        raw: dict[str, object],
    ) -> SignedDurableCompactionCertificate:
        certificate_raw = raw.get(
            "certificate"
        )
        signature_raw = raw.get(
            "signature"
        )
        if (
            not isinstance(
                certificate_raw,
                dict,
            )
            or not isinstance(
                signature_raw,
                dict,
            )
        ):
            raise DurableCompactionCertificateError(
                "certificate record shape invalid"
            )
        certificate = (
            DurableCompactionCertificate(
                int(
                    certificate_raw[
                        "schema_version"
                    ]
                ),
                str(
                    certificate_raw[
                        "certificate_id"
                    ]
                ),
                str(
                    certificate_raw[
                        "chain_id"
                    ]
                ),
                str(
                    certificate_raw[
                        "readiness_digest"
                    ]
                ),
                str(
                    certificate_raw[
                        "retention_plan_digest"
                    ]
                ),
                str(
                    certificate_raw[
                        "compaction_policy_digest"
                    ]
                ),
                int(
                    certificate_raw[
                        "current_sequence"
                    ]
                ),
                str(
                    certificate_raw[
                        "current_root"
                    ]
                ),
                int(
                    certificate_raw[
                        "cutoff_sequence"
                    ]
                ),
                str(
                    certificate_raw[
                        "cutoff_root"
                    ]
                ),
                str(
                    certificate_raw[
                        "archive_id"
                    ]
                ),
                str(
                    certificate_raw[
                        "archive_manifest_digest"
                    ]
                ),
                str(
                    certificate_raw[
                        "protected_roots_digest"
                    ]
                ),
                float(
                    certificate_raw[
                        "issued_at"
                    ]
                ),
                float(
                    certificate_raw[
                        "expires_at"
                    ]
                ),
            )
        )
        return SignedDurableCompactionCertificate(
            certificate,
            cls._signature(
                dict(signature_raw)
            ),
        )

    @staticmethod
    def _head(
        raw: dict[str, object],
    ) -> DurableCompactionCertificateHead:
        return DurableCompactionCertificateHead(
            str(raw["chain_id"]),
            str(raw["certificate_id"]),
            int(raw["current_sequence"]),
            str(raw["current_root"]),
            float(raw["issued_at"]),
        )

    def _verify_signature(
        self,
        item: SignedDurableCompactionCertificate,
    ) -> None:
        cert = item.certificate
        sig = item.signature
        if (
            sig.artifact_type
            != "durable-compaction-readiness"
        ):
            raise DurableCompactionCertificateError(
                "certificate artifact type mismatch"
            )
        if sig.artifact_digest != cert.digest:
            raise DurableCompactionCertificateError(
                "certificate signature digest mismatch"
            )
        expected_metadata = {
            "certificate_id": (
                cert.certificate_id
            ),
            "chain_id": cert.chain_id,
            "authority": (
                "non-destructive-compaction-readiness"
            ),
        }
        if dict(sig.metadata) != expected_metadata:
            raise DurableCompactionCertificateError(
                "certificate signature metadata mismatch"
            )
        try:
            self.signer.verify(sig)
        except ArtifactSignatureError as exc:
            raise DurableCompactionCertificateError(
                "certificate signature verification failed"
            ) from exc

    def _put_immutable(
        self,
        item: SignedDurableCompactionCertificate,
    ) -> bool:
        key = self._certificate_key(
            item.certificate_id
        )
        value = item.to_dict()
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    value,
                )
                return True
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        if not isinstance(
            existing.value,
            dict,
        ):
            raise DurableCompactionCertificateError(
                "certificate record must be mapping"
            )
        current = self._signed(
            dict(existing.value)
        )
        if current != item:
            raise DurableCompactionCertificateError(
                "certificate_id already binds different certificate"
            )
        return False

    def _update_head(
        self,
        item: SignedDurableCompactionCertificate,
    ) -> None:
        cert = item.certificate
        candidate = (
            DurableCompactionCertificateHead(
                cert.chain_id,
                cert.certificate_id,
                cert.current_sequence,
                cert.current_root,
                cert.issued_at,
            )
        )
        key = self._head_key(
            cert.chain_id
        )
        for _ in range(
            self.max_cas_retries
        ):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                try:
                    self.backend.put_if_absent(
                        self.namespace,
                        key,
                        candidate.to_dict(),
                    )
                    return
                except DistributedStateConflict:
                    continue
            if not isinstance(
                record.value,
                dict,
            ):
                raise DurableCompactionCertificateError(
                    "certificate head must be mapping"
                )
            current = self._head(
                dict(record.value)
            )
            if (
                current.current_sequence
                > candidate.current_sequence
            ):
                return
            if (
                current.current_sequence
                == candidate.current_sequence
            ):
                if (
                    current.current_root
                    != candidate.current_root
                ):
                    raise DurableCompactionCertificateError(
                        "same certificate head sequence binds different root"
                    )
                if (
                    current.certificate_id
                    == candidate.certificate_id
                ):
                    return
                # Multiple certificate policies may attest the same chain
                # head. Prefer the most recently issued certificate.
                if (
                    current.issued_at
                    >= candidate.issued_at
                ):
                    return
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=(
                        record.revision
                    ),
                    value=candidate.to_dict(),
                )
                return
            except DistributedStateConflict:
                continue
        raise DurableCompactionCertificateError(
            "certificate head CAS retry budget exhausted"
        )

    def get(
        self,
        certificate_id: str,
    ) -> SignedDurableCompactionCertificate | None:
        record = self.backend.get(
            self.namespace,
            self._certificate_key(
                certificate_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            dict,
        ):
            raise DurableCompactionCertificateError(
                "certificate record must be mapping"
            )
        item = self._signed(
            dict(record.value)
        )
        if (
            item.certificate_id
            != certificate_id
        ):
            raise DurableCompactionCertificateError(
                "certificate record identity mismatch"
            )
        self._verify_signature(item)
        return item

    def latest(
        self,
        chain_id: str,
    ) -> SignedDurableCompactionCertificate | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(
                chain_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            dict,
        ):
            raise DurableCompactionCertificateError(
                "certificate head must be mapping"
            )
        head = self._head(
            dict(record.value)
        )
        if head.chain_id != chain_id:
            raise DurableCompactionCertificateError(
                "certificate head chain identity mismatch"
            )
        item = self.get(
            head.certificate_id
        )
        if item is None:
            raise DurableCompactionCertificateError(
                "certificate head references missing item"
            )
        return item

    def issue(
        self,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        ttl_seconds: float | None = None,
    ) -> SignedDurableCompactionCertificate:
        readiness = (
            self.planner.require_ready(
                retention,
                chain,
            )
        )
        if (
            readiness
            .destructive_action_authorized
        ):
            raise DurableCompactionCertificateError(
                "readiness unexpectedly grants destructive authority"
            )

        ttl = (
            self.ttl_seconds
            if ttl_seconds is None
            else float(ttl_seconds)
        )
        if (
            not math.isfinite(ttl)
            or ttl <= 0.0
            or ttl > self.max_ttl_seconds
        ):
            raise ValueError(
                "certificate ttl outside supported range"
            )

        protected_digest = (
            DurableCompactionCertificate
            .protected_digest(
                readiness
            )
        )
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(
                now,
                (int, float),
            )
            or not math.isfinite(
                float(now)
            )
            or float(now) < 0.0
        ):
            raise DurableCompactionCertificateError(
                "certificate clock returned invalid time"
            )
        now = float(now)

        latest = self.latest(
            readiness.chain_id
        )
        if latest is not None:
            previous = latest.certificate
            if (
                previous.readiness_digest
                == readiness.digest
                and previous.retention_plan_digest
                == readiness.retention_plan_digest
                and previous.compaction_policy_digest
                == readiness.policy_digest
                and previous.current_sequence
                == readiness.current_sequence
                and previous.current_root
                == readiness.current_root
                and previous.cutoff_sequence
                == readiness.cutoff_sequence
                and previous.cutoff_root
                == readiness.cutoff_root
                and previous.archive_id
                == readiness.archive_id
                and previous.archive_manifest_digest
                == readiness.archive_manifest_digest
                and previous.protected_roots_digest
                == protected_digest
                and now < previous.expires_at
            ):
                self._verify_signature(
                    latest
                )
                return latest

        expires_at = now + ttl
        certificate_id = (
            DurableCompactionCertificate
            .derive_id(
                chain_id=readiness.chain_id,
                readiness_digest=(
                    readiness.digest
                ),
                retention_plan_digest=(
                    readiness
                    .retention_plan_digest
                ),
                compaction_policy_digest=(
                    readiness.policy_digest
                ),
                current_sequence=(
                    readiness.current_sequence
                ),
                current_root=(
                    readiness.current_root
                ),
                cutoff_sequence=(
                    readiness.cutoff_sequence
                ),
                cutoff_root=(
                    readiness.cutoff_root
                ),
                archive_id=(
                    readiness.archive_id
                ),
                archive_manifest_digest=(
                    readiness
                    .archive_manifest_digest
                ),
                protected_roots_digest=(
                    protected_digest
                ),
                issued_at=now,
                expires_at=expires_at,
            )
        )
        certificate = (
            DurableCompactionCertificate(
                1,
                certificate_id,
                readiness.chain_id,
                readiness.digest,
                readiness.retention_plan_digest,
                readiness.policy_digest,
                readiness.current_sequence,
                readiness.current_root,
                readiness.cutoff_sequence,
                readiness.cutoff_root,
                readiness.archive_id,
                readiness.archive_manifest_digest,
                protected_digest,
                now,
                expires_at,
            )
        )
        signature = self.signer.sign(
            "durable-compaction-readiness",
            certificate.digest,
            metadata={
                "certificate_id": (
                    certificate_id
                ),
                "chain_id": (
                    readiness.chain_id
                ),
                "authority": (
                    "non-destructive-compaction-readiness"
                ),
            },
        )
        item = (
            SignedDurableCompactionCertificate(
                certificate,
                signature,
            )
        )
        self._put_immutable(item)
        self._update_head(item)
        return item

    def inspect(
        self,
        item: SignedDurableCompactionCertificate,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCompactionCertificateVerification:
        if not isinstance(
            item,
            SignedDurableCompactionCertificate,
        ):
            raise TypeError(
                "item must be SignedDurableCompactionCertificate"
            )
        reasons: list[str] = []
        valid = True
        try:
            self._verify_signature(item)
        except DurableCompactionCertificateError as exc:
            valid = False
            reasons.append(str(exc))

        cert = item.certificate
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(
                now,
                (int, float),
            )
            or not math.isfinite(
                float(now)
            )
            or float(now) < 0.0
        ):
            valid = False
            now = cert.expires_at
            reasons.append(
                "certificate clock returned invalid time"
            )
        now = float(now)
        expired = (
            now >= cert.expires_at
        )

        current_readiness = None
        try:
            current_readiness = (
                self.planner.inspect(
                    retention,
                    chain,
                )
            )
        except Exception as exc:
            reasons.append(
                "current compaction readiness inspection failed: "
                f"{type(exc).__name__}"
            )

        current_digest = (
            ""
            if current_readiness is None
            else current_readiness.digest
        )
        current = bool(
            current_readiness is not None
            and current_readiness.ready
            and current_readiness.digest
            == cert.readiness_digest
            and retention.digest
            == cert.retention_plan_digest
            and current_readiness.policy_digest
            == cert.compaction_policy_digest
            and current_readiness.current_sequence
            == cert.current_sequence
            and current_readiness.current_root
            == cert.current_root
            and current_readiness.cutoff_sequence
            == cert.cutoff_sequence
            and current_readiness.cutoff_root
            == cert.cutoff_root
            and current_readiness.archive_id
            == cert.archive_id
            and current_readiness.archive_manifest_digest
            == cert.archive_manifest_digest
            and DurableCompactionCertificate
            .protected_digest(
                current_readiness
            )
            == cert.protected_roots_digest
        )
        if not current:
            reasons.append(
                "certificate no longer matches current compaction readiness"
            )
        if expired:
            reasons.append(
                "certificate has expired"
            )
        if cert.destructive_action_authorized:
            valid = False
            reasons.append(
                "certificate unexpectedly grants destructive authority"
            )

        return (
            DurableCompactionCertificateVerification(
                valid,
                current,
                expired,
                cert.certificate_id,
                cert.chain_id,
                cert.readiness_digest,
                current_digest,
                tuple(reasons),
            )
        )

    def require_current(
        self,
        item: SignedDurableCompactionCertificate,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCompactionCertificateVerification:
        report = self.inspect(
            item,
            retention,
            chain,
        )
        if not report.allowed:
            detail = (
                report.reasons[0]
                if report.reasons
                else "compaction readiness certificate is invalid"
            )
            raise DurableCompactionCertificateError(
                detail
            )
        return report
