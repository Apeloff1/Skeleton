"""Explicit signed authority for destructive hot-tier evidence pruning.

Compaction readiness and its existing certificate are intentionally
non-destructive.  This module adds a second authority boundary.  A pruning
authorization can only be issued while a signed compaction-readiness
certificate is still current for the exact live head, retention plan, cutoff,
archive manifest, and protected-root set.

The authorization is short-lived and resumable: the same authorization may
continue one durable pruning operation after a worker restart, but it does not
implicitly authorize a different operation or a changed live head.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import secrets
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_checkpoint import CheckpointableEvidenceChain
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificate,
    DurableCompactionCertificateError,
    DurableCompactionCertificateStore,
    SignedDurableCompactionCertificate,
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
class DurablePruningAuthorization:
    schema_version: int
    authorization_id: str
    chain_id: str
    certificate_id: str
    certificate_digest: str
    retention_plan_digest: str
    compaction_policy_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    previous_floor_sequence: int
    previous_floor_root: str
    delete_count: int
    archive_id: str
    archive_manifest_digest: str
    protected_roots_digest: str
    operator_id: str
    max_delete_items: int
    nonce: str
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported pruning authorization schema"
            )
        for name in (
            "authorization_id",
            "certificate_id",
            "certificate_digest",
            "retention_plan_digest",
            "compaction_policy_digest",
            "current_root",
            "cutoff_root",
            "previous_floor_root",
            "archive_manifest_digest",
            "protected_roots_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        _identity(
            "archive_id",
            self.archive_id,
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
        for name in (
            "current_sequence",
            "cutoff_sequence",
            "previous_floor_sequence",
            "delete_count",
            "max_delete_items",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )
        if self.cutoff_sequence > self.current_sequence:
            raise ValueError(
                "pruning cutoff exceeds authorized head"
            )
        if self.previous_floor_sequence >= self.cutoff_sequence:
            raise ValueError(
                "pruning authorization must advance previous floor"
            )
        if self.delete_count != (
            self.cutoff_sequence
            - self.previous_floor_sequence
        ):
            raise ValueError(
                "delete_count differs from authorized floor interval"
            )
        if self.delete_count > self.max_delete_items:
            raise ValueError(
                "pruning interval exceeds authorization delete bound"
            )
        if (
            self.previous_floor_sequence == 0
            and self.previous_floor_root != "0" * 64
        ):
            raise ValueError(
                "genesis previous floor must use genesis root"
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
                "authorization expiry must follow issue time"
            )

    @staticmethod
    def derive_id(
        *,
        chain_id: str,
        certificate_id: str,
        certificate_digest: str,
        retention_plan_digest: str,
        compaction_policy_digest: str,
        current_sequence: int,
        current_root: str,
        cutoff_sequence: int,
        cutoff_root: str,
        previous_floor_sequence: int,
        previous_floor_root: str,
        delete_count: int,
        archive_id: str,
        archive_manifest_digest: str,
        protected_roots_digest: str,
        operator_id: str,
        max_delete_items: int,
        nonce: str,
        issued_at: float,
        expires_at: float,
    ) -> str:
        payload = {
            "chain_id": chain_id,
            "certificate_id": certificate_id,
            "certificate_digest": certificate_digest,
            "retention_plan_digest": retention_plan_digest,
            "compaction_policy_digest": compaction_policy_digest,
            "current_sequence": current_sequence,
            "current_root": current_root,
            "cutoff_sequence": cutoff_sequence,
            "cutoff_root": cutoff_root,
            "previous_floor_sequence": previous_floor_sequence,
            "previous_floor_root": previous_floor_root,
            "delete_count": delete_count,
            "archive_id": archive_id,
            "archive_manifest_digest": archive_manifest_digest,
            "protected_roots_digest": protected_roots_digest,
            "operator_id": operator_id,
            "max_delete_items": max_delete_items,
            "nonce": nonce,
            "issued_at": float(issued_at),
            "expires_at": float(expires_at),
            "authority": "destructive-hot-tier-pruning",
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def destructive_action_authorized(self) -> bool:
        return True

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "chain_id": self.chain_id,
            "certificate_id": self.certificate_id,
            "certificate_digest": self.certificate_digest,
            "retention_plan_digest": self.retention_plan_digest,
            "compaction_policy_digest": self.compaction_policy_digest,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "previous_floor_sequence": self.previous_floor_sequence,
            "previous_floor_root": self.previous_floor_root,
            "delete_count": self.delete_count,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
            "protected_roots_digest": self.protected_roots_digest,
            "operator_id": self.operator_id,
            "max_delete_items": self.max_delete_items,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "destructive_action_authorized": True,
            "authority": "destructive-hot-tier-pruning",
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
class SignedDurablePruningAuthorization:
    authorization: DurablePruningAuthorization
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.authorization,
            DurablePruningAuthorization,
        ):
            raise TypeError(
                "authorization must be DurablePruningAuthorization"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    @property
    def authorization_id(self) -> str:
        return self.authorization.authorization_id

    @property
    def destructive_action_authorized(self) -> bool:
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "authorization": self.authorization.to_dict(),
            "signature": self.signature.to_dict(),
            "destructive_action_authorized": True,
        }


@dataclass(frozen=True)
class DurablePruningAuthorizationVerification:
    valid: bool
    current: bool
    expired: bool
    authorization_id: str
    chain_id: str
    certificate_id: str
    current_head_sequence: int
    current_head_root: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "valid",
            "current",
            "expired",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(
                    f"{name} must be bool"
                )
        for name in (
            "authorization_id",
            "certificate_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.current_head_sequence, bool)
            or not isinstance(self.current_head_sequence, int)
            or self.current_head_sequence < 0
        ):
            raise ValueError(
                "current_head_sequence must be non-negative"
            )
        object.__setattr__(
            self,
            "current_head_root",
            _digest(
                "current_head_root",
                self.current_head_root,
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
        return self.allowed

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "current": self.current,
            "expired": self.expired,
            "allowed": self.allowed,
            "destructive_action_authorized": (
                self.destructive_action_authorized
            ),
            "authorization_id": self.authorization_id,
            "chain_id": self.chain_id,
            "certificate_id": self.certificate_id,
            "current_head_sequence": self.current_head_sequence,
            "current_head_root": self.current_head_root,
            "reasons": list(self.reasons),
        }


class DurablePruningAuthorizationError(RuntimeError):
    pass


class DurablePruningAuthorizationStore:
    """Issue and verify short-lived destructive pruning authority."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        certificates: DurableCompactionCertificateStore,
        *,
        namespace: str = "shell-ai-durable-pruning-authorizations",
        ttl_seconds: float = 120.0,
        max_ttl_seconds: float = 900.0,
        max_delete_items: int = 100_000,
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
            raise TypeError("signer must be ArtifactSigner")
        if not isinstance(
            certificates,
            DurableCompactionCertificateStore,
        ):
            raise TypeError(
                "certificates must be DurableCompactionCertificateStore"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid pruning authorization namespace"
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
        self.ttl_seconds = float(ttl_seconds)
        self.max_ttl_seconds = float(
            max_ttl_seconds
        )
        if self.ttl_seconds > self.max_ttl_seconds:
            raise ValueError(
                "ttl_seconds exceeds maximum"
            )
        if (
            isinstance(max_delete_items, bool)
            or not isinstance(max_delete_items, int)
            or max_delete_items <= 0
        ):
            raise ValueError(
                "max_delete_items must be positive integer"
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
        self.certificates = certificates
        self.namespace = namespace
        self.max_delete_items = max_delete_items
        self._clock = clock
        self._nonce_factory = (
            nonce_factory
            or (lambda: secrets.token_hex(16))
        )

    @staticmethod
    def _authorization_key(
        authorization_id: str,
    ) -> str:
        return (
            "authorization:"
            + _digest(
                "authorization_id",
                authorization_id,
            )
        )

    @staticmethod
    def _head_key(chain_id: str) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        return (
            "head:"
            + hashlib.sha256(
                chain_id.encode()
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
            dict(raw.get("metadata", {})),
            str(raw["signature"]),
        )

    @classmethod
    def _signed(
        cls,
        raw: dict[str, object],
    ) -> SignedDurablePruningAuthorization:
        auth_raw = raw.get("authorization")
        sig_raw = raw.get("signature")
        if not isinstance(auth_raw, dict):
            raise DurablePruningAuthorizationError(
                "authorization record shape invalid"
            )
        if not isinstance(sig_raw, dict):
            raise DurablePruningAuthorizationError(
                "authorization signature shape invalid"
            )
        auth = DurablePruningAuthorization(
            int(auth_raw["schema_version"]),
            str(auth_raw["authorization_id"]),
            str(auth_raw["chain_id"]),
            str(auth_raw["certificate_id"]),
            str(auth_raw["certificate_digest"]),
            str(auth_raw["retention_plan_digest"]),
            str(auth_raw["compaction_policy_digest"]),
            int(auth_raw["current_sequence"]),
            str(auth_raw["current_root"]),
            int(auth_raw["cutoff_sequence"]),
            str(auth_raw["cutoff_root"]),
            int(auth_raw["previous_floor_sequence"]),
            str(auth_raw["previous_floor_root"]),
            int(auth_raw["delete_count"]),
            str(auth_raw["archive_id"]),
            str(auth_raw["archive_manifest_digest"]),
            str(auth_raw["protected_roots_digest"]),
            str(auth_raw["operator_id"]),
            int(auth_raw["max_delete_items"]),
            str(auth_raw["nonce"]),
            float(auth_raw["issued_at"]),
            float(auth_raw["expires_at"]),
        )
        return SignedDurablePruningAuthorization(
            auth,
            cls._signature(sig_raw),
        )

    def _verify_signature(
        self,
        item: SignedDurablePruningAuthorization,
    ) -> None:
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise DurablePruningAuthorizationError(
                "pruning authorization signature verification failed"
            ) from exc
        if (
            item.signature.artifact_type
            != "durable-pruning-authorization"
        ):
            raise DurablePruningAuthorizationError(
                "unexpected pruning authorization artifact type"
            )
        if (
            item.signature.artifact_digest
            != item.authorization.digest
        ):
            raise DurablePruningAuthorizationError(
                "pruning authorization signature digest mismatch"
            )
        metadata = dict(
            item.signature.metadata
        )
        if (
            metadata.get("authorization_id")
            != item.authorization.authorization_id
            or metadata.get("chain_id")
            != item.authorization.chain_id
            or metadata.get("operator_id")
            != item.authorization.operator_id
        ):
            raise DurablePruningAuthorizationError(
                "pruning authorization signature metadata mismatch"
            )

    def get(
        self,
        authorization_id: str,
    ) -> SignedDurablePruningAuthorization | None:
        record = self.backend.get(
            self.namespace,
            self._authorization_key(
                authorization_id
            ),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurablePruningAuthorizationError(
                "authorization record must be mapping"
            )
        item = self._signed(
            dict(record.value)
        )
        if (
            item.authorization.authorization_id
            != authorization_id
        ):
            raise DurablePruningAuthorizationError(
                "authorization record identity mismatch"
            )
        self._verify_signature(item)
        return item

    def latest(
        self,
        chain_id: str,
    ) -> SignedDurablePruningAuthorization | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, str):
            raise DurablePruningAuthorizationError(
                "authorization head must contain authorization id"
            )
        item = self.get(record.value)
        if item is None:
            raise DurablePruningAuthorizationError(
                "authorization head references missing item"
            )
        if item.authorization.chain_id != chain_id:
            raise DurablePruningAuthorizationError(
                "authorization head chain mismatch"
            )
        return item

    def _store(
        self,
        item: SignedDurablePruningAuthorization,
    ) -> None:
        key = self._authorization_key(
            item.authorization_id
        )
        payload = item.to_dict()
        try:
            self.backend.put_if_absent(
                self.namespace,
                key,
                payload,
            )
        except DistributedStateConflict:
            current = self.backend.get(
                self.namespace,
                key,
            )
            if (
                current is None
                or current.value != payload
            ):
                raise DurablePruningAuthorizationError(
                    "authorization id already binds different payload"
                )

        head_key = self._head_key(
            item.authorization.chain_id
        )
        for _ in range(32):
            current = self.backend.get(
                self.namespace,
                head_key,
            )
            revision = (
                0
                if current is None
                else current.revision
            )
            try:
                if revision == 0:
                    self.backend.put_if_absent(
                        self.namespace,
                        head_key,
                        item.authorization_id,
                    )
                else:
                    self.backend.compare_and_swap(
                        self.namespace,
                        head_key,
                        expected_revision=revision,
                        value=item.authorization_id,
                    )
                return
            except DistributedStateConflict:
                continue
        raise DurablePruningAuthorizationError(
            "authorization head CAS retry budget exhausted"
        )

    def issue(
        self,
        certificate: SignedDurableCompactionCertificate,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
        *,
        operator_id: str,
        ttl_seconds: float | None = None,
        max_delete_items: int | None = None,
    ) -> SignedDurablePruningAuthorization:
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        verification = (
            self.certificates.require_current(
                certificate,
                retention,
                chain,
            )
        )
        if not verification.allowed:
            raise DurablePruningAuthorizationError(
                "compaction certificate is not current"
            )
        if (
            certificate.destructive_action_authorized
            or certificate.certificate
            .destructive_action_authorized
        ):
            raise DurablePruningAuthorizationError(
                "readiness certificate unexpectedly grants destructive authority"
            )

        cert = certificate.certificate
        limit = (
            self.max_delete_items
            if max_delete_items is None
            else max_delete_items
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or limit > self.max_delete_items
        ):
            raise ValueError(
                "max_delete_items outside supported range"
            )
        floor_method = getattr(
            chain,
            "hot_floor",
            None,
        )
        if callable(floor_method):
            floor = floor_method()
            active_method = getattr(
                chain,
                "_hot_floor_active",
                None,
            )
            if (
                floor.sequence > 0
                and callable(active_method)
                and not active_method(floor)
            ):
                raise DurablePruningAuthorizationError(
                    "existing hot floor is not active; prior pruning must be resolved"
                )
            previous_floor_sequence = int(
                floor.sequence
            )
            previous_floor_root = str(
                floor.root_hash
            )
        else:
            previous_floor_sequence = 0
            previous_floor_root = "0" * 64
        delete_count = (
            cert.cutoff_sequence
            - previous_floor_sequence
        )
        if delete_count <= 0:
            raise DurablePruningAuthorizationError(
                "compaction cutoff does not advance current hot floor"
            )
        if delete_count > limit:
            raise DurablePruningAuthorizationError(
                "compaction interval exceeds requested delete bound"
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
                "authorization ttl outside supported range"
            )
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or float(now) < 0.0
        ):
            raise DurablePruningAuthorizationError(
                "authorization clock returned invalid time"
            )
        now = float(now)
        expires_at = now + ttl
        nonce = self._nonce_factory()
        _identity(
            "nonce",
            nonce,
            maximum=256,
        )
        protected_digest = (
            DurableCompactionCertificate
            .protected_digest(
                self.certificates
                .planner.require_ready(
                    retention,
                    chain,
                )
            )
        )
        authorization_id = (
            DurablePruningAuthorization
            .derive_id(
                chain_id=cert.chain_id,
                certificate_id=cert.certificate_id,
                certificate_digest=cert.digest,
                retention_plan_digest=(
                    cert.retention_plan_digest
                ),
                compaction_policy_digest=(
                    cert.compaction_policy_digest
                ),
                current_sequence=cert.current_sequence,
                current_root=cert.current_root,
                cutoff_sequence=cert.cutoff_sequence,
                cutoff_root=cert.cutoff_root,
                previous_floor_sequence=(
                    previous_floor_sequence
                ),
                previous_floor_root=(
                    previous_floor_root
                ),
                delete_count=delete_count,
                archive_id=cert.archive_id,
                archive_manifest_digest=(
                    cert.archive_manifest_digest
                ),
                protected_roots_digest=(
                    protected_digest
                ),
                operator_id=operator_id,
                max_delete_items=limit,
                nonce=nonce,
                issued_at=now,
                expires_at=expires_at,
            )
        )
        auth = DurablePruningAuthorization(
            1,
            authorization_id,
            cert.chain_id,
            cert.certificate_id,
            cert.digest,
            cert.retention_plan_digest,
            cert.compaction_policy_digest,
            cert.current_sequence,
            cert.current_root,
            cert.cutoff_sequence,
            cert.cutoff_root,
            previous_floor_sequence,
            previous_floor_root,
            delete_count,
            cert.archive_id,
            cert.archive_manifest_digest,
            protected_digest,
            operator_id,
            limit,
            nonce,
            now,
            expires_at,
        )
        signature = self.signer.sign(
            "durable-pruning-authorization",
            auth.digest,
            metadata={
                "authorization_id": (
                    authorization_id
                ),
                "chain_id": cert.chain_id,
                "operator_id": operator_id,
                "authority": (
                    "destructive-hot-tier-pruning"
                ),
            },
        )
        item = SignedDurablePruningAuthorization(
            auth,
            signature,
        )
        self._store(item)
        return item

    def inspect(
        self,
        item: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurablePruningAuthorizationVerification:
        if not isinstance(
            item,
            SignedDurablePruningAuthorization,
        ):
            raise TypeError(
                "item must be SignedDurablePruningAuthorization"
            )
        reasons: list[str] = []
        valid = True
        try:
            self._verify_signature(item)
        except DurablePruningAuthorizationError as exc:
            valid = False
            reasons.append(str(exc))

        auth = item.authorization
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or float(now) < 0.0
        ):
            valid = False
            now = auth.expires_at
            reasons.append(
                "authorization clock returned invalid time"
            )
        now = float(now)
        expired = now >= auth.expires_at

        head = chain.head()
        current_sequence = int(head.sequence)
        current_root = str(head.root_hash)

        certificate = None
        try:
            certificate = self.certificates.get(
                auth.certificate_id
            )
        except (
            DurableCompactionCertificateError,
            ValueError,
            TypeError,
        ) as exc:
            reasons.append(
                "referenced compaction certificate lookup failed: "
                f"{type(exc).__name__}"
            )

        current = False
        if certificate is None:
            reasons.append(
                "referenced compaction certificate is missing"
            )
        else:
            try:
                cert_verification = (
                    self.certificates
                    .require_current(
                        certificate,
                        retention,
                        chain,
                    )
                )
                cert = certificate.certificate
                current = bool(
                    cert_verification.allowed
                    and certificate.certificate_id
                    == auth.certificate_id
                    and cert.digest
                    == auth.certificate_digest
                    and cert.chain_id
                    == auth.chain_id
                    and cert.retention_plan_digest
                    == auth.retention_plan_digest
                    and cert.compaction_policy_digest
                    == auth.compaction_policy_digest
                    and cert.current_sequence
                    == auth.current_sequence
                    and cert.current_root
                    == auth.current_root
                    and cert.cutoff_sequence
                    == auth.cutoff_sequence
                    and cert.cutoff_root
                    == auth.cutoff_root
                    and (
                        not callable(
                            getattr(
                                chain,
                                "hot_floor",
                                None,
                            )
                        )
                        or (
                            chain.hot_floor().sequence
                            == auth.previous_floor_sequence
                            and chain.hot_floor().root_hash
                            == auth.previous_floor_root
                        )
                    )
                    and auth.delete_count
                    == (
                        auth.cutoff_sequence
                        - auth.previous_floor_sequence
                    )
                    and cert.archive_id
                    == auth.archive_id
                    and cert.archive_manifest_digest
                    == auth.archive_manifest_digest
                    and cert.protected_roots_digest
                    == auth.protected_roots_digest
                    and current_sequence
                    == auth.current_sequence
                    and current_root
                    == auth.current_root
                )
            except Exception as exc:
                reasons.append(
                    "current pruning authority verification failed: "
                    f"{type(exc).__name__}"
                )
        if not current:
            reasons.append(
                "authorization no longer matches current compaction authority"
            )
        if expired:
            reasons.append(
                "pruning authorization has expired"
            )

        return DurablePruningAuthorizationVerification(
            valid,
            current,
            expired,
            auth.authorization_id,
            auth.chain_id,
            auth.certificate_id,
            current_sequence,
            current_root,
            tuple(reasons),
        )

    def require_current(
        self,
        item: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurablePruningAuthorizationVerification:
        report = self.inspect(
            item,
            retention,
            chain,
        )
        if not report.allowed:
            detail = (
                report.reasons[0]
                if report.reasons
                else "pruning authorization is invalid"
            )
            raise DurablePruningAuthorizationError(
                detail
            )
        return report
