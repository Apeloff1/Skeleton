"""Deterministic reverse-engineering campaign manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class CampaignArtifact:
    artifact_id: str
    kind: str
    digest: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.kind:
            raise ReverseEngineeringError("campaign artifact identity is required")
        if not is_sha256_digest(self.digest):
            raise ReverseEngineeringError("campaign artifact digest must be sha256 hex")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ReverseEngineeringError("campaign artifact dependencies must be unique")


@dataclass(frozen=True)
class CampaignManifest:
    campaign_id: str
    protocol_digest: str
    target_id: str
    artifacts: tuple[CampaignArtifact, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "protocol_digest": self.protocol_digest,
            "target_id": self.target_id,
            "artifacts": [
                {
                    "artifact_id": artifact.artifact_id,
                    "kind": artifact.kind,
                    "digest": artifact.digest,
                    "depends_on": list(artifact.depends_on),
                }
                for artifact in self.artifacts
            ],
            "digest": self.digest,
        }


def build_campaign_manifest(
    campaign_id: str,
    protocol_digest: str,
    target_id: str,
    artifacts: Sequence[CampaignArtifact],
) -> CampaignManifest:
    if not campaign_id or not target_id:
        raise ReverseEngineeringError("campaign identity and target are required")
    if not is_sha256_digest(protocol_digest):
        raise ReverseEngineeringError("protocol_digest must be sha256 hex")
    if not artifacts:
        raise ReverseEngineeringError("campaign requires artifacts")
    ids = [artifact.artifact_id for artifact in artifacts]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("campaign artifact ids must be unique")
    known = set(ids)
    for artifact in artifacts:
        missing = set(artifact.depends_on) - known
        if missing:
            raise ReverseEngineeringError(
                f"campaign artifact {artifact.artifact_id!r} has unknown dependencies"
            )
        if artifact.artifact_id in artifact.depends_on:
            raise ReverseEngineeringError("campaign artifact cannot depend on itself")
    ordered = tuple(sorted(artifacts, key=lambda item: item.artifact_id))
    payload = {
        "campaign_id": campaign_id,
        "protocol_digest": protocol_digest,
        "target_id": target_id,
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "digest": artifact.digest,
                "depends_on": list(sorted(artifact.depends_on)),
            }
            for artifact in ordered
        ],
    }
    return CampaignManifest(
        campaign_id=campaign_id,
        protocol_digest=protocol_digest,
        target_id=target_id,
        artifacts=ordered,
        digest=stable_digest(payload),
    )
