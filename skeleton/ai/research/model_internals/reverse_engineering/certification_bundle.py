"""Canonical certification bundle for a closed reverse-engineering campaign."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest

_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class CertificationArtifact:
    artifact_id: str
    kind: str
    digest: str

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.kind:
            raise ReverseEngineeringError("certification artifact identity is required")
        if not is_sha256_digest(self.digest):
            raise ReverseEngineeringError("certification artifact digest must be sha256 hex")


@dataclass(frozen=True)
class CertificationBundle:
    campaign_id: str
    exact_head_sha: str
    artifacts: tuple[CertificationArtifact, ...]
    required_kinds: tuple[str, ...]
    complete: bool
    missing_kinds: tuple[str, ...]
    bundle_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "exact_head_sha": self.exact_head_sha,
            "artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "kind": item.kind,
                    "digest": item.digest,
                }
                for item in self.artifacts
            ],
            "required_kinds": list(self.required_kinds),
            "complete": self.complete,
            "missing_kinds": list(self.missing_kinds),
            "bundle_digest": self.bundle_digest,
        }


def build_certification_bundle(
    *,
    campaign_id: str,
    exact_head_sha: str,
    artifacts: Sequence[CertificationArtifact],
    required_kinds: Sequence[str] = (
        "protocol",
        "authorization",
        "evidence",
        "replay",
        "reproducibility",
        "falsification",
        "replication",
        "lineage",
        "claim_closure",
        "closure_certificate",
        "campaign_verification",
    ),
) -> CertificationBundle:
    if not campaign_id:
        raise ReverseEngineeringError("certification bundle requires campaign_id")
    if not _GIT_SHA.fullmatch(exact_head_sha):
        raise ReverseEngineeringError("exact_head_sha must be a full lowercase git SHA")
    if not artifacts:
        raise ReverseEngineeringError("certification bundle requires artifacts")
    ids = [item.artifact_id for item in artifacts]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("certification artifact ids must be unique")
    required = tuple(dict.fromkeys(required_kinds))
    if any(not kind for kind in required):
        raise ReverseEngineeringError("required certification kinds must be non-empty")

    ordered = tuple(sorted(artifacts, key=lambda item: item.artifact_id))
    present = {item.kind for item in ordered}
    missing = tuple(sorted(set(required) - present))
    payload = {
        "campaign_id": campaign_id,
        "exact_head_sha": exact_head_sha,
        "required_kinds": list(required),
        "artifacts": [
            {
                "artifact_id": item.artifact_id,
                "kind": item.kind,
                "digest": item.digest,
            }
            for item in ordered
        ],
    }
    return CertificationBundle(
        campaign_id=campaign_id,
        exact_head_sha=exact_head_sha,
        artifacts=ordered,
        required_kinds=required,
        complete=not missing,
        missing_kinds=missing,
        bundle_digest=stable_digest(payload),
    )


def verify_certification_bundle(bundle: CertificationBundle) -> bool:
    try:
        rebuilt = build_certification_bundle(
            campaign_id=bundle.campaign_id,
            exact_head_sha=bundle.exact_head_sha,
            artifacts=bundle.artifacts,
            required_kinds=bundle.required_kinds,
        )
    except ReverseEngineeringError:
        return False
    return (
        rebuilt.bundle_digest == bundle.bundle_digest
        and rebuilt.complete == bundle.complete
        and rebuilt.missing_kinds == bundle.missing_kinds
    )
