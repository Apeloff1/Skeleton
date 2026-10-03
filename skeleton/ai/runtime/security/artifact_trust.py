"""Load-time supply-chain trust admission for release artifacts.

Build/release evidence remains owned by :mod:`skeleton.release.evidence`.
This module composes that canonical release-ready decision with exact observed
artifact bytes, trusted signature-verifier implementations, and explicit
revocation/quarantine policy before a runtime may load an artifact.

No cryptographic primitive is implemented here. Signature verification is
performed by a trusted verifier supplied by the deployment trust root.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping, Protocol, Sequence, runtime_checkable

from skeleton.release.evidence import (
    ReleaseEvidence,
    evidence_digest,
    evaluate_release_ready,
    parse_evidence,
    sha256_bytes,
)


class ArtifactTrustError(RuntimeError):
    """Artifact trust admission is malformed or rejected."""


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _text(name: str, value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactTrustError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise ArtifactTrustError(f"{name} must be normalized bounded text")
    return result


def _token(name: str, value: object) -> str:
    result = _text(name, value, maximum=256)
    if _TOKEN.fullmatch(result) is None:
        raise ArtifactTrustError(f"{name} is not a canonical token")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if _SHA.fullmatch(result) is None:
        raise ArtifactTrustError(f"{name} must be lowercase sha256")
    return result


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactTrustError("trust payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    artifact_id: str
    artifact_digest: str
    signer_id: str
    key_id: str
    algorithm: str
    signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _token("artifact_id", self.artifact_id))
        object.__setattr__(
            self, "artifact_digest", _sha("artifact_digest", self.artifact_digest)
        )
        object.__setattr__(self, "signer_id", _token("signer_id", self.signer_id))
        object.__setattr__(self, "key_id", _token("key_id", self.key_id))
        object.__setattr__(self, "algorithm", _token("algorithm", self.algorithm))
        object.__setattr__(
            self, "signature", _text("signature", self.signature, maximum=8192)
        )

    def signed_identity(self) -> dict[str, str]:
        return {
            "schema_version": "skeleton.artifact_signature_identity.v1",
            "artifact_id": self.artifact_id,
            "artifact_digest": self.artifact_digest,
            "signer_id": self.signer_id,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
        }


@runtime_checkable
class ArtifactSignatureVerifier(Protocol):
    """Deployment-provided cryptographic verifier bound to one trust identity."""

    @property
    def verifier_id(self) -> str: ...

    @property
    def signer_id(self) -> str: ...

    @property
    def key_id(self) -> str: ...

    @property
    def algorithm(self) -> str: ...

    def verify(self, envelope: SignatureEnvelope) -> bool: ...


@dataclass(frozen=True, slots=True)
class ArtifactTrustPolicy:
    trusted_signer_keys: tuple[tuple[str, str], ...]
    allowed_algorithms: tuple[str, ...]
    minimum_signatures: int = 1
    revoked_artifact_digests: tuple[str, ...] = ()
    revoked_key_ids: tuple[str, ...] = ()
    quarantined_artifact_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        pairs: list[tuple[str, str]] = []
        for raw in self.trusted_signer_keys:
            if not isinstance(raw, tuple) or len(raw) != 2:
                raise ArtifactTrustError(
                    "trusted_signer_keys must contain (signer_id, key_id) tuples"
                )
            pair = (_token("signer_id", raw[0]), _token("key_id", raw[1]))
            pairs.append(pair)
        if not pairs:
            raise ArtifactTrustError("at least one trusted signer/key is required")
        if len(pairs) != len(set(pairs)):
            raise ArtifactTrustError("trusted signer/key pairs must be unique")
        object.__setattr__(self, "trusted_signer_keys", tuple(sorted(pairs)))

        algorithms = tuple(
            sorted({_token("algorithm", item) for item in self.allowed_algorithms})
        )
        if not algorithms:
            raise ArtifactTrustError("allowed_algorithms must not be empty")
        object.__setattr__(self, "allowed_algorithms", algorithms)

        if (
            isinstance(self.minimum_signatures, bool)
            or not isinstance(self.minimum_signatures, int)
            or self.minimum_signatures < 1
            or self.minimum_signatures > len(pairs)
        ):
            raise ArtifactTrustError("minimum_signatures is outside trusted signer set")

        for field_name in (
            "revoked_artifact_digests",
            "quarantined_artifact_digests",
        ):
            values = tuple(
                sorted({_sha(field_name, item) for item in getattr(self, field_name)})
            )
            object.__setattr__(self, field_name, values)
        revoked_keys = tuple(
            sorted({_token("revoked_key_id", item) for item in self.revoked_key_ids})
        )
        object.__setattr__(self, "revoked_key_ids", revoked_keys)

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": "skeleton.artifact_trust_policy.v1",
                "trusted_signer_keys": [list(item) for item in self.trusted_signer_keys],
                "allowed_algorithms": list(self.allowed_algorithms),
                "minimum_signatures": self.minimum_signatures,
                "revoked_artifact_digests": list(self.revoked_artifact_digests),
                "revoked_key_ids": list(self.revoked_key_ids),
                "quarantined_artifact_digests": list(
                    self.quarantined_artifact_digests
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class ArtifactTrustReceipt:
    artifact_id: str
    artifact_digest: str
    source_commit: str
    release_evidence_digest: str
    trust_policy_digest: str
    verified_signature_ids: tuple[str, ...]
    accepted: bool
    reasons: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": "skeleton.artifact_trust_receipt.v1",
                "artifact_id": self.artifact_id,
                "artifact_digest": self.artifact_digest,
                "source_commit": self.source_commit,
                "release_evidence_digest": self.release_evidence_digest,
                "trust_policy_digest": self.trust_policy_digest,
                "verified_signature_ids": list(self.verified_signature_ids),
                "accepted": self.accepted,
                "reasons": list(self.reasons),
            }
        )

    def require_accepted(self) -> "ArtifactTrustReceipt":
        if not self.accepted:
            raise ArtifactTrustError(
                "artifact trust admission rejected: " + ",".join(self.reasons)
            )
        return self


def _document(
    evidence: ReleaseEvidence | Mapping[str, object] | str | bytes,
) -> ReleaseEvidence:
    if isinstance(evidence, ReleaseEvidence):
        return evidence
    return parse_evidence(evidence)


def admit_release_artifact(
    *,
    evidence: ReleaseEvidence | Mapping[str, object] | str | bytes,
    expected_commit: str,
    artifact_id: str,
    artifact_bytes: bytes,
    signatures: Sequence[SignatureEnvelope],
    verifiers: Mapping[str, ArtifactSignatureVerifier],
    policy: ArtifactTrustPolicy,
) -> ArtifactTrustReceipt:
    """Fail closed unless an exact release artifact is trusted at load time."""

    if not isinstance(policy, ArtifactTrustPolicy):
        raise TypeError("policy must be ArtifactTrustPolicy")
    if not isinstance(artifact_bytes, bytes):
        raise TypeError("artifact_bytes must be bytes")
    target_id = _token("artifact_id", artifact_id)
    document = _document(evidence)
    gate = evaluate_release_ready(document, expected_commit=expected_commit)
    reasons = list(gate.reasons)

    records = [item for item in document.artifacts if item.artifact_id == target_id]
    if len(records) != 1:
        reasons.append("artifact-id-cardinality-invalid")
        declared_digest = sha256_bytes(artifact_bytes)
    else:
        record = records[0]
        declared_digest = record.sha256
        observed_digest = sha256_bytes(artifact_bytes)
        if observed_digest != record.sha256:
            reasons.append("artifact-digest-mismatch")
        if len(artifact_bytes) != record.size:
            reasons.append("artifact-size-mismatch")

    if declared_digest in policy.revoked_artifact_digests:
        reasons.append("artifact-revoked")
    if declared_digest in policy.quarantined_artifact_digests:
        reasons.append("artifact-quarantined")

    signature_rows = tuple(signatures)
    if any(not isinstance(item, SignatureEnvelope) for item in signature_rows):
        raise TypeError("signatures must contain SignatureEnvelope values")

    identities = [
        (item.signer_id, item.key_id, item.algorithm)
        for item in signature_rows
    ]
    if len(identities) != len(set(identities)):
        reasons.append("duplicate-signature-identity")

    verified: list[str] = []
    accepted_pairs: set[tuple[str, str]] = set()
    for signature in signature_rows:
        signature_id = f"{signature.signer_id}:{signature.key_id}:{signature.algorithm}"
        if signature.artifact_id != target_id:
            reasons.append(f"signature-artifact-id-mismatch:{signature_id}")
            continue
        if signature.artifact_digest != declared_digest:
            reasons.append(f"signature-artifact-digest-mismatch:{signature_id}")
            continue
        pair = (signature.signer_id, signature.key_id)
        if pair not in policy.trusted_signer_keys:
            reasons.append(f"signature-signer-key-untrusted:{signature_id}")
            continue
        if signature.key_id in policy.revoked_key_ids:
            reasons.append(f"signature-key-revoked:{signature_id}")
            continue
        if signature.algorithm not in policy.allowed_algorithms:
            reasons.append(f"signature-algorithm-untrusted:{signature_id}")
            continue

        verifier = verifiers.get(signature.signer_id)
        if verifier is None:
            reasons.append(f"signature-verifier-missing:{signature_id}")
            continue
        try:
            verifier_identity = (
                _token("verifier_id", verifier.verifier_id),
                _token("verifier_signer_id", verifier.signer_id),
                _token("verifier_key_id", verifier.key_id),
                _token("verifier_algorithm", verifier.algorithm),
            )
        except Exception:
            reasons.append(f"signature-verifier-identity-invalid:{signature_id}")
            continue
        if verifier_identity[1:] != (
            signature.signer_id,
            signature.key_id,
            signature.algorithm,
        ):
            reasons.append(f"signature-verifier-identity-mismatch:{signature_id}")
            continue
        try:
            ok = verifier.verify(signature)
        except Exception:
            reasons.append(f"signature-verification-error:{signature_id}")
            continue
        if ok is not True:
            reasons.append(f"signature-verification-failed:{signature_id}")
            continue
        accepted_pairs.add(pair)
        verified.append(
            _canonical_digest(
                {
                    "signature_identity": signature.signed_identity(),
                    "verifier_id": verifier_identity[0],
                }
            )
        )

    if len(accepted_pairs) < policy.minimum_signatures:
        reasons.append("signature-threshold-not-met")

    normalized = tuple(sorted(set(reasons)))
    return ArtifactTrustReceipt(
        artifact_id=target_id,
        artifact_digest=declared_digest,
        source_commit=document.source_commit,
        release_evidence_digest=evidence_digest(document),
        trust_policy_digest=policy.digest,
        verified_signature_ids=tuple(sorted(set(verified))),
        accepted=not normalized,
        reasons=normalized,
    )


__all__ = [
    "ArtifactSignatureVerifier",
    "ArtifactTrustError",
    "ArtifactTrustPolicy",
    "ArtifactTrustReceipt",
    "SignatureEnvelope",
    "admit_release_artifact",
]
