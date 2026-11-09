from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.engineering_standards_review import EngineeringStandardsReviewError,build_engineering_standards_review

def d(x): return hashlib.sha256(x.encode()).hexdigest()
def evidence():
    return {k:d(k) for k in (
        "model_card","dataset_card","tool_card","agent_card","component_health","dependency_health",
        "provider_risk","provider_failover","offline_mode","air_gap","edge_deployment",
        "enterprise_deployment","identity_federation","administration_plane",
    )}
def test_review_binds_all_fourteen_standards_surfaces_to_one_revision():
    r=build_engineering_standards_review(review_id="oct2026",source_revision="a"*40,subject_id="platform",evidence_digests=evidence(),blocker_codes=(),producer_id="builder",independent_verifier_id="verifier")
    assert r.status=="ready_for_independent_closure" and len(r.evidence_digests)==14 and len(r.digest)==64
    assert r.promotion_authority is False and r.production_authority is False
def test_missing_standard_surface_fails_closed():
    data=evidence(); data.pop("air_gap")
    with pytest.raises(EngineeringStandardsReviewError,match="exactly cover"):
        build_engineering_standards_review(review_id="r",source_revision="b"*40,subject_id="p",evidence_digests=data,blocker_codes=(),producer_id="a",independent_verifier_id="b")
def test_verifier_must_be_independent():
    with pytest.raises(EngineeringStandardsReviewError,match="differ from producer"):
        build_engineering_standards_review(review_id="r",source_revision="c"*40,subject_id="p",evidence_digests=evidence(),blocker_codes=(),producer_id="same",independent_verifier_id="same")
def test_blockers_cannot_be_hidden():
    r=build_engineering_standards_review(review_id="r",source_revision="d"*40,subject_id="p",evidence_digests=evidence(),blocker_codes=("provider-risk-high",),producer_id="a",independent_verifier_id="b")
    assert r.status=="blocked" and r.blocker_codes==("provider-risk-high",)
