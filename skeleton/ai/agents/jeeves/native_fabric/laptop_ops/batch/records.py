"""Immutable all-20 source-only diagnostic receipts with mandatory holds."""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.native_fabric.laptop_ops.contracts import (
    DomainVerdict, LaptopGateHold, sha,
)
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains
from .limits import DOMAIN_COUNT, TOTAL_STAGES

HOLDS = (
    "real native GGUF inference not witnessed by source-only checks",
    "installed model and source rights require independent attestation",
    "physical Windows/WSL2 device, memory pressure and cancellation unqualified",
    "final-head CI, security and release approval outstanding",
)


@dataclass(frozen=True, slots=True)
class SourceBundle:
    domains: tuple[DomainVerdict, ...]
    manifest_sha256: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        sha(self.manifest_sha256)
        sha(self.evidence_sha256)
        if (type(self.domains) is not tuple
                or len(self.domains) != DOMAIN_COUNT
                or any(type(v) is not DomainVerdict for v in self.domains)
                or tuple(v.domain for v in self.domains) != list_domains()):
            raise LaptopGateHold("all twenty ordered domain verdicts required")

    @property
    def accepted_source_only(self) -> bool:
        return all(v.accepted for v in self.domains)

    def to_record(self) -> dict[str, object]:
        """Source evidence only; no user-controlled release or provider flag."""
        return {
            "schema": "jeeves.laptop_ops.bundle.v1",
            "accepted_source_only": self.accepted_source_only,
            "domain_count": DOMAIN_COUNT,
            "stage_count": TOTAL_STAGES,
            "manifest_sha256": self.manifest_sha256,
            "evidence_sha256": self.evidence_sha256,
            "domains": [v.to_record() for v in self.domains],
            "operator_claims_are_not_authority": True,
            "real_native_inference_witnessed": False,
            "physical_device_qualified": False,
            "release_certified": False,
            "holds": list(HOLDS),
        }


__all__ = ["SourceBundle", "HOLDS"]
