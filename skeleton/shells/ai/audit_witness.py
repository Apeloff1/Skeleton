"""Monotonic signed audit witnesses for rollback-resistant AI shell evidence.

The ordinary audit-anchor chain proves internal hash continuity.  It does not,
by itself, prove that a durable backend was not restored to an older valid
snapshot.  This module publishes independently signed, monotonically numbered
witnesses through a compare-and-swap state backend.  A process restart can
therefore require the latest witnessed audit root instead of trusting whatever
older chain root happens to be present.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    VersionedValue,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(name: str, value: str, *, optional: bool = False) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class AIAuditWitness:
    schema_version: int
    sequence: int
    audit_root: str
    previous_witness_digest: str
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    observed_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AI audit witness schema")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("audit witness sequence must be positive")
        object.__setattr__(self, "audit_root", _digest("audit_root", self.audit_root))
        object.__setattr__(
            self,
            "previous_witness_digest",
            _digest(
                "previous_witness_digest",
                self.previous_witness_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "runtime_trust_digest",
            _digest(
                "runtime_trust_digest",
                self.runtime_trust_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "release_evidence_digest",
            _digest(
                "release_evidence_digest",
                self.release_evidence_digest,
                optional=True,
            ),
        )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or self.observed_at < 0
        ):
            raise ValueError("audit witness observed_at must be non-negative")
        if self.sequence == 1 and self.previous_witness_digest:
            raise ValueError("first audit witness may not have a predecessor")
        if self.sequence > 1 and not self.previous_witness_digest:
            raise ValueError("later audit witness requires predecessor digest")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "audit_root": self.audit_root,
            "previous_witness_digest": self.previous_witness_digest,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "observed_at": self.observed_at,
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
class SignedAIAuditWitness:
    witness: AIAuditWitness
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if self.signature.artifact_type != "ai-audit-witness":
            raise ValueError("invalid audit witness artifact type")
        if self.signature.artifact_digest != self.witness.digest:
            raise ValueError("audit witness signature digest mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "witness": self.witness.to_dict(),
            "witness_digest": self.witness.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class AuditWitnessHead:
    sequence: int
    witness_digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("audit witness head sequence must be positive")
        object.__setattr__(
            self,
            "witness_digest",
            _digest("witness_digest", self.witness_digest),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "witness_digest": self.witness_digest,
        }


@dataclass(frozen=True)
class AuditWitnessVerification:
    ok: bool
    reasons: tuple[str, ...]
    head_sequence: int = 0
    head_digest: str = ""
    audit_root: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "reasons": list(self.reasons),
            "head_sequence": self.head_sequence,
            "head_digest": self.head_digest,
            "audit_root": self.audit_root,
        }


class AIAuditWitnessStore:
    """CAS-published immutable signed witnesses with bounded full verification."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-audit-witness",
        head_key: str = "head",
        max_witnesses: int = 100_000,
        max_retries: int = 8,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid audit witness namespace")
        if not head_key or len(head_key) > 128:
            raise ValueError("invalid audit witness head key")
        if (
            isinstance(max_witnesses, bool)
            or not isinstance(max_witnesses, int)
            or max_witnesses <= 0
        ):
            raise ValueError("max_witnesses must be positive")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 64
        ):
            raise ValueError("max_retries outside supported range")
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.head_key = head_key
        self.max_witnesses = max_witnesses
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def _node_key(sequence: int) -> str:
        return f"witness:{sequence:020d}"

    @staticmethod
    def _signature(raw: dict[str, object]) -> SignedArtifact:
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            dict(raw.get("metadata", {})),
            str(raw["signature"]),
        )

    @classmethod
    def _signed_witness(cls, value: object) -> SignedAIAuditWitness:
        if not isinstance(value, dict):
            raise ValueError("audit witness record must be mapping")
        raw_witness = value.get("witness")
        raw_signature = value.get("signature")
        if not isinstance(raw_witness, dict) or not isinstance(raw_signature, dict):
            raise ValueError("audit witness record shape invalid")
        witness = AIAuditWitness(
            int(raw_witness["schema_version"]),
            int(raw_witness["sequence"]),
            str(raw_witness["audit_root"]),
            str(raw_witness.get("previous_witness_digest", "")),
            str(raw_witness.get("runtime_trust_digest", "")),
            str(raw_witness.get("release_evidence_digest", "")),
            float(raw_witness["observed_at"]),
        )
        return SignedAIAuditWitness(
            witness,
            cls._signature(dict(raw_signature)),
        )

    @staticmethod
    def _head(value: object) -> AuditWitnessHead:
        if not isinstance(value, dict):
            raise ValueError("audit witness head must be mapping")
        return AuditWitnessHead(
            int(value["sequence"]),
            str(value["witness_digest"]),
        )

    def current_head(
        self,
    ) -> tuple[int, AuditWitnessHead] | None:
        record = self.backend.get(self.namespace, self.head_key)
        if record is None:
            return None
        return record.revision, self._head(record.value)

    def get(self, sequence: int) -> SignedAIAuditWitness:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError("audit witness sequence must be positive")
        record = self.backend.get(self.namespace, self._node_key(sequence))
        if record is None:
            raise KeyError(sequence)
        item = self._signed_witness(record.value)
        if item.witness.sequence != sequence:
            raise ValueError("audit witness sequence/key mismatch")
        return item

    def _build(
        self,
        *,
        sequence: int,
        audit_root: str,
        previous_witness_digest: str,
        runtime_trust_digest: str,
        release_evidence_digest: str,
    ) -> SignedAIAuditWitness:
        witness = AIAuditWitness(
            1,
            sequence,
            audit_root,
            previous_witness_digest,
            runtime_trust_digest,
            release_evidence_digest,
            self._clock(),
        )
        signature = self.signer.sign(
            "ai-audit-witness",
            witness.digest,
            metadata={"sequence": str(sequence)},
        )
        return SignedAIAuditWitness(witness, signature)

    def find(
        self,
        audit_root: str,
        *,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> SignedAIAuditWitness | None:
        audit_root = _digest("audit_root", audit_root)
        runtime_trust_digest = _digest(
            "runtime_trust_digest",
            runtime_trust_digest,
            optional=True,
        )
        release_evidence_digest = _digest(
            "release_evidence_digest",
            release_evidence_digest,
            optional=True,
        )
        current = self.current_head()
        if current is None:
            return None
        _, head = current
        if head.sequence > self.max_witnesses:
            raise RuntimeError("audit witness head exceeds configured bound")
        for sequence in range(head.sequence, 0, -1):
            item = self.get(sequence)
            witness = item.witness
            if witness.audit_root != audit_root:
                continue
            if witness.runtime_trust_digest != runtime_trust_digest:
                continue
            if witness.release_evidence_digest != release_evidence_digest:
                continue
            try:
                self.signer.verify(item.signature)
            except ArtifactSignatureError as exc:
                raise RuntimeError(
                    "matching audit witness signature verification failed"
                ) from exc
            return item
        return None

    def publish_once(
        self,
        audit_root: str,
        *,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> SignedAIAuditWitness:
        existing = self.find(
            audit_root,
            runtime_trust_digest=runtime_trust_digest,
            release_evidence_digest=release_evidence_digest,
        )
        if existing is not None:
            return existing
        return self.publish(
            audit_root,
            runtime_trust_digest=runtime_trust_digest,
            release_evidence_digest=release_evidence_digest,
        )

    def publish(
        self,
        audit_root: str,
        *,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> SignedAIAuditWitness:
        audit_root = _digest("audit_root", audit_root)
        runtime_trust_digest = _digest(
            "runtime_trust_digest",
            runtime_trust_digest,
            optional=True,
        )
        release_evidence_digest = _digest(
            "release_evidence_digest",
            release_evidence_digest,
            optional=True,
        )

        for _ in range(self.max_retries):
            head_record = self.backend.get(self.namespace, self.head_key)
            if head_record is None:
                sequence = 1
                previous_digest = ""
                expected_revision = 0
            else:
                head = self._head(head_record.value)
                if head.sequence >= self.max_witnesses:
                    raise RuntimeError("audit witness capacity exhausted")
                sequence = head.sequence + 1
                previous_digest = head.witness_digest
                expected_revision = head_record.revision

            item = self._build(
                sequence=sequence,
                audit_root=audit_root,
                previous_witness_digest=previous_digest,
                runtime_trust_digest=runtime_trust_digest,
                release_evidence_digest=release_evidence_digest,
            )
            node_key = self._node_key(sequence)
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    node_key,
                    item.to_dict(),
                )
            except DistributedStateConflict:
                # Another writer may have won this sequence.  Reload the head
                # and retry; immutable node collisions are never overwritten.
                continue

            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    self.head_key,
                    expected_revision=expected_revision,
                    value=AuditWitnessHead(
                        sequence,
                        item.witness.digest,
                    ).to_dict(),
                )
                return item
            except DistributedStateConflict:
                # The node is an unreachable orphan if another writer advanced
                # the head first.  It remains immutable evidence but is not part
                # of the canonical witness chain.
                continue

        raise DistributedStateConflict(
            "audit witness publish retry bound exceeded"
        )

    def require_witness(
        self,
        item: SignedAIAuditWitness,
    ) -> SignedAIAuditWitness:
        if not isinstance(item, SignedAIAuditWitness):
            raise TypeError("item must be SignedAIAuditWitness")
        current = self.current_head()
        if current is None:
            raise RuntimeError("audit witness chain is empty")
        _, head = current
        if item.witness.sequence > head.sequence:
            raise RuntimeError("audit witness is newer than canonical head")
        canonical = self.get(item.witness.sequence)
        if canonical.witness.digest != item.witness.digest:
            raise RuntimeError("audit witness is not canonical at its sequence")
        if canonical.signature != item.signature:
            raise RuntimeError("audit witness signature differs from canonical record")
        try:
            self.signer.verify(canonical.signature)
        except ArtifactSignatureError as exc:
            raise RuntimeError("audit witness signature verification failed") from exc
        verification = self.verify()
        if not verification.ok:
            raise RuntimeError(
                "audit witness chain integrity verification failed"
            )
        return canonical

    def require_current_root(
        self,
        audit_root: str,
        *,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> SignedAIAuditWitness:
        current = self.current_head()
        if current is None:
            raise RuntimeError("no audit witness has been published")
        _, head = current
        item = self.get(head.sequence)
        if item.witness.digest != head.witness_digest:
            raise RuntimeError("audit witness head digest mismatch")
        if item.witness.audit_root != _digest("audit_root", audit_root):
            raise RuntimeError("audit root rollback or drift detected")
        if (
            runtime_trust_digest
            and item.witness.runtime_trust_digest
            != _digest("runtime_trust_digest", runtime_trust_digest)
        ):
            raise RuntimeError("audit witness runtime trust mismatch")
        if (
            release_evidence_digest
            and item.witness.release_evidence_digest
            != _digest("release_evidence_digest", release_evidence_digest)
        ):
            raise RuntimeError("audit witness release evidence mismatch")
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise RuntimeError("audit witness signature verification failed") from exc
        return item

    def verify(self) -> AuditWitnessVerification:
        current = self.current_head()
        if current is None:
            return AuditWitnessVerification(True, ())
        _, head = current
        if head.sequence > self.max_witnesses:
            return AuditWitnessVerification(
                False,
                ("audit witness head exceeds configured bound",),
                head.sequence,
                head.witness_digest,
            )

        reasons: list[str] = []
        previous = ""
        final_root = ""
        for sequence in range(1, head.sequence + 1):
            try:
                item = self.get(sequence)
            except (KeyError, ValueError, TypeError) as exc:
                reasons.append(
                    f"audit witness {sequence} unavailable or invalid: {type(exc).__name__}"
                )
                break
            witness = item.witness
            if witness.previous_witness_digest != previous:
                reasons.append(
                    f"audit witness {sequence} predecessor mismatch"
                )
                break
            try:
                self.signer.verify(item.signature)
            except ArtifactSignatureError:
                reasons.append(
                    f"audit witness {sequence} signature invalid"
                )
                break
            previous = witness.digest
            final_root = witness.audit_root

        if not reasons and previous != head.witness_digest:
            reasons.append("audit witness head does not match canonical chain")
        return AuditWitnessVerification(
            not reasons,
            tuple(reasons),
            head.sequence,
            head.witness_digest,
            final_root,
        )
