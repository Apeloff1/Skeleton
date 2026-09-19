"""Signed correlated trust snapshots for AI shell operations and incident audit."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.ai.audit_witness import AuditWitnessVerification
from skeleton.shells.ai.authority_health import AuthorityHealthReport
from skeleton.shells.ai.runtime_trust import RuntimeTrustReport
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)


def _digest(name: str, value: str, *, optional: bool = False) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Opaque 64-character authority digest; production values remain hashes.
    return value.lower()


@dataclass(frozen=True)
class AITrustSnapshot:
    schema_version: int
    service_phase: str
    runtime_trust_digest: str
    authority_health_policy_digest: str
    audit_witness_head_digest: str = ""
    audit_witness_sequence: int = 0
    release_evidence_digest: str = ""
    sandbox_binding_digest: str = ""
    observed_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AI trust snapshot schema")
        if not self.service_phase or len(self.service_phase) > 64:
            raise ValueError("invalid service_phase")
        object.__setattr__(
            self,
            "runtime_trust_digest",
            _digest("runtime_trust_digest", self.runtime_trust_digest),
        )
        object.__setattr__(
            self,
            "authority_health_policy_digest",
            _digest(
                "authority_health_policy_digest",
                self.authority_health_policy_digest,
            ),
        )
        object.__setattr__(
            self,
            "audit_witness_head_digest",
            _digest(
                "audit_witness_head_digest",
                self.audit_witness_head_digest,
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
        object.__setattr__(
            self,
            "sandbox_binding_digest",
            _digest(
                "sandbox_binding_digest",
                self.sandbox_binding_digest,
                optional=True,
            ),
        )
        if (
            isinstance(self.audit_witness_sequence, bool)
            or not isinstance(self.audit_witness_sequence, int)
            or self.audit_witness_sequence < 0
        ):
            raise ValueError("audit_witness_sequence must be non-negative")
        if bool(self.audit_witness_head_digest) != (
            self.audit_witness_sequence > 0
        ):
            raise ValueError(
                "audit witness head digest and sequence must be present together"
            )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or self.observed_at < 0
        ):
            raise ValueError("trust snapshot observed_at must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "service_phase": self.service_phase,
            "runtime_trust_digest": self.runtime_trust_digest,
            "authority_health_policy_digest": self.authority_health_policy_digest,
            "audit_witness_head_digest": self.audit_witness_head_digest,
            "audit_witness_sequence": self.audit_witness_sequence,
            "release_evidence_digest": self.release_evidence_digest,
            "sandbox_binding_digest": self.sandbox_binding_digest,
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
class SignedAITrustSnapshot:
    snapshot: AITrustSnapshot
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if self.signature.artifact_type != "ai-trust-snapshot":
            raise ValueError("invalid AI trust snapshot artifact type")
        if self.signature.artifact_digest != self.snapshot.digest:
            raise ValueError("AI trust snapshot signature digest mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "snapshot_digest": self.snapshot.digest,
            "signature": self.signature.to_dict(),
        }


class AITrustSnapshotBuilder:
    """Build and verify a portable signed trust-state commitment."""

    def __init__(
        self,
        signer: ArtifactSigner,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.signer = signer
        self._clock = clock

    def build(
        self,
        *,
        service_phase: str,
        runtime_trust: RuntimeTrustReport,
        authority_health: AuthorityHealthReport,
        audit_witness: AuditWitnessVerification | None = None,
        sandbox_binding_digest: str = "",
        require_healthy: bool = True,
    ) -> SignedAITrustSnapshot:
        if not runtime_trust.allowed or runtime_trust.epoch is None:
            raise RuntimeError("runtime trust report is not admissible")
        if require_healthy and not authority_health.ok:
            raise RuntimeError("authority health report is not healthy")
        if audit_witness is not None and not audit_witness.ok:
            raise RuntimeError("audit witness verification failed")

        release_digest = runtime_trust.epoch.release_evidence_digest
        witness_digest = ""
        witness_sequence = 0
        if audit_witness is not None:
            witness_digest = audit_witness.head_digest
            witness_sequence = audit_witness.head_sequence

        snapshot = AITrustSnapshot(
            1,
            service_phase,
            runtime_trust.epoch.digest,
            authority_health.policy_digest,
            witness_digest,
            witness_sequence,
            release_digest,
            sandbox_binding_digest,
            self._clock(),
        )
        signature = self.signer.sign(
            "ai-trust-snapshot",
            snapshot.digest,
            metadata={
                "service_phase": service_phase,
                "runtime_trust": snapshot.runtime_trust_digest,
            },
        )
        return SignedAITrustSnapshot(snapshot, signature)

    def verify(
        self,
        item: SignedAITrustSnapshot,
        *,
        expected_runtime_trust_digest: str = "",
        expected_audit_head_digest: str = "",
        expected_release_evidence_digest: str = "",
    ) -> None:
        if not isinstance(item, SignedAITrustSnapshot):
            raise ValueError("item must be SignedAITrustSnapshot")
        self.signer.verify(item.signature)
        if (
            expected_runtime_trust_digest
            and item.snapshot.runtime_trust_digest
            != _digest(
                "expected_runtime_trust_digest",
                expected_runtime_trust_digest,
            )
        ):
            raise RuntimeError("trust snapshot runtime epoch mismatch")
        if (
            expected_audit_head_digest
            and item.snapshot.audit_witness_head_digest
            != _digest(
                "expected_audit_head_digest",
                expected_audit_head_digest,
            )
        ):
            raise RuntimeError("trust snapshot audit witness mismatch")
        if (
            expected_release_evidence_digest
            and item.snapshot.release_evidence_digest
            != _digest(
                "expected_release_evidence_digest",
                expected_release_evidence_digest,
            )
        ):
            raise RuntimeError("trust snapshot release evidence mismatch")

    def inspect_signature(self, item: SignedAITrustSnapshot) -> bool:
        try:
            self.verify(item)
        except (ArtifactSignatureError, RuntimeError, ValueError, TypeError):
            return False
        return True
