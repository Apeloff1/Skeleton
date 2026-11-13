"""Operator-signed source preflight before real GGUF package activation.

Original source bytes, HMAC approval, tenant, subject, expiration and
descriptor-anchored path custody are checked before model startup. The
subsequent native evidence provider must reverify those same bytes at source
selection and inside the durable SQLite commit boundary.

This preflight does not grant a tool, prove third-party rights or execute AI.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    Scope,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    SignedSourceManifest,
    verify_signed_manifest,
    ingest_authorized_sources,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,
)


class NativeSourcePreflightHold(ValueError):
    """Pre-native signed-source custody cannot be established."""


@dataclass(frozen=True, slots=True)
class NativeSourcePreflight:
    scope: Scope
    manifest_sha256: str
    issued_at: int
    expires_at: int
    source_count: int
    original_byte_hashes: tuple[tuple[str, str], ...]

    def verify_active_model(self, identity: Identity) -> None:
        if not isinstance(identity, Identity):
            raise NativeSourcePreflightHold("actual native model identity required")
        if (
            identity.tenant != self.scope.tenant
            or identity.subject != self.scope.subject
            or identity.model_sha256 != self.scope.model_sha256
            or identity.tokenizer_sha256 != self.scope.tokenizer_sha256
        ):
            raise NativeSourcePreflightHold(
                "real installed native model differs from signed source approval"
            )

    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "jeeves.signed_source_preflight.v1",
            "manifest_sha256": self.manifest_sha256,
            "scope_sha256": self.scope.digest(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "source_count": self.source_count,
            "original_byte_hashes": [
                {"source_id": source, "sha256": sha}
                for source, sha in self.original_byte_hashes
            ],
            "operator_source_bytes_verified": True,
            "independent_legal_rights_verified": False,
            "native_model_loaded": False,
            "tool_grant_issued": False,
            "release_certified": False,
        }


def verify_sources_before_native_start(
    *,
    source_root: Path,
    signed_manifest: bytes,
    operator_key: bytes,
    tenant: str,
    subject: str,
    observed_at: int,
    maximum_sources: int = 6,
) -> NativeSourcePreflight:
    if not isinstance(source_root, Path) or not source_root.is_absolute():
        raise NativeSourcePreflightHold("explicit absolute source root required")
    if type(signed_manifest) is not bytes or not 1 <= len(signed_manifest) <= 32768:
        raise NativeSourcePreflightHold("bounded operator-signed manifest required")
    if type(operator_key) is not bytes or not 32 <= len(operator_key) <= 4096:
        raise NativeSourcePreflightHold("independent operator key required")
    if type(observed_at) is not int or observed_at < 1:
        raise NativeSourcePreflightHold("trusted observed timestamp required")
    if type(maximum_sources) is not int or not 1 <= maximum_sources <= 6:
        raise NativeSourcePreflightHold("signed source preflight capacity exceeded")

    approval = verify_signed_manifest(
        signed_manifest, operator_key, observed_at=observed_at,
    )
    if not isinstance(approval, SignedSourceManifest):
        raise NativeSourcePreflightHold("operator source approval missing typed authority")
    if (approval.scope.tenant, approval.scope.subject) != (tenant, subject):
        raise NativeSourcePreflightHold("signed source belongs to another principal")
    if len(approval.sources) > maximum_sources:
        raise NativeSourcePreflightHold("operator signed sources exceed requested ceiling")
    index = ingest_authorized_sources(
        source_root, approval,
        scope=approval.scope, observed_at=observed_at,
    )
    original = tuple(
        (item.source_id, item.sha256) for item in approval.sources
    )
    if len(index.documents) != len(original):
        raise NativeSourcePreflightHold("source index lost approved original bytes")
    if any(
        source_id not in index.documents
        or index.documents[source_id].source.sha256 != original_sha
        for source_id, original_sha in original
    ):
        raise NativeSourcePreflightHold("operator original-byte digest mismatch")
    return NativeSourcePreflight(
        scope=approval.scope,
        manifest_sha256=sha256(signed_manifest).hexdigest(),
        issued_at=approval.issued_at,
        expires_at=approval.expires_at,
        source_count=len(original),
        original_byte_hashes=original,
    )


__all__ = [
    "NativeSourcePreflightHold", "NativeSourcePreflight",
    "verify_sources_before_native_start",
]
