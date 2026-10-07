"""Tamper-evident closure certificates for fully governed claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ClosureCertificate:
    claim_id: str
    claim_digest: str
    closure_digest: str
    campaign_audit_digest: str
    bundle_digest: str
    lineage_digest: str
    certificate_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_digest": self.claim_digest,
            "closure_digest": self.closure_digest,
            "campaign_audit_digest": self.campaign_audit_digest,
            "bundle_digest": self.bundle_digest,
            "lineage_digest": self.lineage_digest,
            "certificate_digest": self.certificate_digest,
        }


def issue_closure_certificate(
    *,
    claim_id: str,
    claim_digest: str,
    closure_digest: str,
    campaign_audit_digest: str,
    bundle_digest: str,
    lineage_digest: str,
    claim_closed: bool,
    campaign_ready: bool,
    bundle_valid: bool,
    lineage_closed: bool,
) -> ClosureCertificate:
    if not claim_id:
        raise ReverseEngineeringError("closure certificate requires claim_id")
    for digest in (
        claim_digest,
        closure_digest,
        campaign_audit_digest,
        bundle_digest,
        lineage_digest,
    ):
        if not is_sha256_digest(digest):
            raise ReverseEngineeringError("closure certificate digests must be sha256 hex")
    if not (claim_closed and campaign_ready and bundle_valid and lineage_closed):
        raise ReverseEngineeringError(
            "closure certificate requires closed claim, ready campaign, valid bundle, and closed lineage"
        )
    payload = {
        "claim_id": claim_id,
        "claim_digest": claim_digest,
        "closure_digest": closure_digest,
        "campaign_audit_digest": campaign_audit_digest,
        "bundle_digest": bundle_digest,
        "lineage_digest": lineage_digest,
    }
    return ClosureCertificate(
        claim_id=claim_id,
        claim_digest=claim_digest,
        closure_digest=closure_digest,
        campaign_audit_digest=campaign_audit_digest,
        bundle_digest=bundle_digest,
        lineage_digest=lineage_digest,
        certificate_digest=stable_digest(payload),
    )


def verify_closure_certificate(certificate: ClosureCertificate) -> bool:
    for digest in (
        certificate.claim_digest,
        certificate.closure_digest,
        certificate.campaign_audit_digest,
        certificate.bundle_digest,
        certificate.lineage_digest,
        certificate.certificate_digest,
    ):
        if not is_sha256_digest(digest):
            return False
    expected = stable_digest(
        {
            "claim_id": certificate.claim_id,
            "claim_digest": certificate.claim_digest,
            "closure_digest": certificate.closure_digest,
            "campaign_audit_digest": certificate.campaign_audit_digest,
            "bundle_digest": certificate.bundle_digest,
            "lineage_digest": certificate.lineage_digest,
        }
    )
    return expected == certificate.certificate_digest
