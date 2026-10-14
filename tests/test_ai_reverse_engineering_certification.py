from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.ai.research.model_internals.reverse_engineering.campaign_verification import (
    CampaignVerificationControl,
    verify_campaign,
)
from skeleton.ai.research.model_internals.reverse_engineering.claim_dependencies import (
    ClaimDependency,
    analyze_claim_dependencies,
)
from skeleton.ai.research.model_internals.reverse_engineering.closure_certificate import (
    issue_closure_certificate,
    verify_closure_certificate,
)
from skeleton.ai.research.model_internals.reverse_engineering.contracts import (
    ReverseEngineeringError,
)
from skeleton.ai.research.model_internals.reverse_engineering.evidence_supersession import (
    EvidenceRevision,
    analyze_evidence_supersession,
)
from skeleton.ai.research.model_internals.reverse_engineering.protocol_integrity import (
    build_protocol_manifest,
    verify_protocol_manifest,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_evidence_supersession_preserves_single_active_tip():
    report = analyze_evidence_supersession(
        (
            EvidenceRevision("v1", d("v1")),
            EvidenceRevision("v2", d("v2"), "v1"),
            EvidenceRevision("v3", d("v3"), "v2"),
        )
    )
    assert report.valid is True
    assert report.active_tip_ids == ("v3",)
    assert report.root_count == 1


def test_claim_dependency_rejection_propagates():
    report = analyze_claim_dependencies(
        (
            ClaimDependency("base", "rejected"),
            ClaimDependency("derived", "supported", ("base",)),
        )
    )
    derived = next(item for item in report.results if item.claim_id == "derived")
    assert derived.effective_status == "rejected"
    assert derived.blocking_dependency_ids == ("base",)


def test_protocol_manifest_detects_parameter_tampering():
    manifest = build_protocol_manifest("p1", "v1", {"repeats": 3, "mode": "deterministic"})
    assert verify_protocol_manifest(manifest) is True
    tampered = replace(manifest, parameters={"repeats": 4, "mode": "deterministic"})
    assert verify_protocol_manifest(tampered) is False


def test_closure_certificate_requires_all_governance_controls():
    certificate = issue_closure_certificate(
        claim_id="c1",
        claim_digest=d("claim"),
        closure_digest=d("closure"),
        campaign_audit_digest=d("audit"),
        bundle_digest=d("bundle"),
        lineage_digest=d("lineage"),
        claim_closed=True,
        campaign_ready=True,
        bundle_valid=True,
        lineage_closed=True,
    )
    assert verify_closure_certificate(certificate) is True
    assert verify_closure_certificate(replace(certificate, claim_id="other")) is False

    with pytest.raises(ReverseEngineeringError, match="requires closed claim"):
        issue_closure_certificate(
            claim_id="c2",
            claim_digest=d("claim2"),
            closure_digest=d("closure2"),
            campaign_audit_digest=d("audit2"),
            bundle_digest=d("bundle2"),
            lineage_digest=d("lineage2"),
            claim_closed=False,
            campaign_ready=True,
            bundle_valid=True,
            lineage_closed=True,
        )


def test_campaign_verification_requires_every_critical_category():
    required = (
        "authorization",
        "protocol",
        "coverage",
        "power",
        "replay",
        "reproducibility",
        "lineage",
        "falsification",
        "replication",
        "freshness",
        "closure",
    )
    controls = tuple(
        CampaignVerificationControl(category, category, d(category), True)
        for category in required
    )
    report = verify_campaign(controls)
    assert report.verified is True
    assert report.failed_count == 0

    blocked = verify_campaign(tuple(control for control in controls if control.category != "power"))
    assert blocked.status == "blocked"
