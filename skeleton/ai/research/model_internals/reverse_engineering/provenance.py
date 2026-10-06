"""Provenance gate for locally inspected reverse-engineering artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .contracts import AuthorizationScope, ReverseEngineeringError


class RightsBasis(str, Enum):
    OWNED = "owned"
    OPEN_SOURCE = "open_source"
    LICENSED = "licensed"
    PUBLIC_SPECIFICATION = "public_specification"


@dataclass(frozen=True)
class ArtifactProvenance:
    artifact_id: str
    source_uri: str
    rights_basis: RightsBasis
    license_id: str | None = None
    content_sha256: str | None = None
    contains_credentials: bool = False
    contains_personal_data: bool = False

    def __post_init__(self) -> None:
        if not self.artifact_id.strip() or not self.source_uri.strip():
            raise ReverseEngineeringError("artifact provenance requires identity and source_uri")
        if self.content_sha256 is not None and len(self.content_sha256) != 64:
            raise ReverseEngineeringError("content_sha256 must be a sha256 hex digest")
        if self.rights_basis in {RightsBasis.OPEN_SOURCE, RightsBasis.LICENSED} and not self.license_id:
            raise ReverseEngineeringError("licensed/open-source artifacts require license_id")


@dataclass(frozen=True)
class ProvenanceGate:
    authorization: AuthorizationScope

    def admit(self, provenance: ArtifactProvenance) -> None:
        if not self.authorization.artifact_inspection:
            raise ReverseEngineeringError("artifact inspection is not authorized for this session")
        if provenance.contains_credentials:
            raise ReverseEngineeringError("credential-bearing artifacts are not admissible")
        if provenance.contains_personal_data:
            raise ReverseEngineeringError("personal-data-bearing artifacts are not admissible")
        if provenance.rights_basis not in set(RightsBasis):
            raise ReverseEngineeringError("unsupported rights basis")

    def receipt(self, provenance: ArtifactProvenance) -> str:
        self.admit(provenance)
        payload = "|".join(
            (
                provenance.artifact_id,
                provenance.source_uri,
                provenance.rights_basis.value,
                provenance.license_id or "",
                provenance.content_sha256 or "",
            )
        )
        return sha256(payload.encode("utf-8")).hexdigest()
