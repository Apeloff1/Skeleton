from datetime import UTC, datetime, timedelta

from core.claim_truth_ledger import ClaimTruthLedger
from core.contradiction_resolver import ContradictionResolver
from core.knowledge_augmented_jeeves import KnowledgeAugmentedJeeves
from core.source_lineage import SourceLineageGraph
from core.truth_verifier import EvidenceItem, EvidenceKind
from core.verified_curiosity import VerifiedCuriosityEngine


def _evidence(source: str, group: str, claim: str, *, kind=EvidenceKind.PRIMARY_EMPIRICAL, supports=True, parents=()):
    return {
        "source_id": source, "source": source, "locator": f"doi:{source}", "kind": kind.value,
        "independence_group": group, "quality": 1.0, "supports": supports,
        "reproducible": kind == EvidenceKind.REPLICATION, "peer_reviewed": True, "primary": True,
        "provenance_verified": True, "preregistered": True, "data_available": True, "code_available": True,
        "sample_size": 500, "uncertainty_reported": True, "parent_source_ids": list(parents),
        "citation_binding": {"binding_method": "direct_quote", "evidence_span": claim, "mapping_rationale": ""},
    }


def _promote(engine: VerifiedCuriosityEngine, claim: str, *, derivative=False):
    engine.observe_prompt("empirical latency research")
    inquiry = engine.next_inquiry(); assert inquiry is not None
    primary = _evidence("study-primary", "lab-a", claim)
    replication = _evidence("study-replication", "lab-b", claim, kind=EvidenceKind.REPLICATION,
                            parents=("study-primary",) if derivative else ())
    record = engine.accept_finding(inquiry, {
        "summary": "Two provenance-verified empirical sources evaluate latency.",
        "claims": [claim], "falsifiable": {claim: True},
        "claim_evidence": {claim: [primary, replication]},
    })
    return record


def test_source_lineage_cascades_retraction_without_erasing_history(tmp_path):
    graph = SourceLineageGraph(tmp_path)
    graph.register("raw", source_kind="official_data", locator="dataset:v1")
    graph.register("analysis", source_kind="secondary_analysis", locator="paper:1", parent_ids=("raw",))
    graph.register("review", source_kind="systematic_review", locator="review:1", parent_ids=("analysis",))
    affected = graph.retract("raw", "source owner withdrew corrupted dataset")
    assert affected == ("analysis", "raw", "review")
    assert graph.get("raw").retracted is True
    assert graph.get("analysis").retraction_reason.startswith("upstream retraction")
    assert graph.stats()["retracted"] == 3


def test_truth_ledger_expires_without_deleting_verification_history(tmp_path):
    ledger = ClaimTruthLedger(tmp_path, default_valid_days=2)
    old = datetime.now(UTC) - timedelta(days=5)
    state = ledger.record(claim="Measured output is 10 units.", verification_state="verified",
                          verification_attestation_sha256="a" * 64, evidence_record_ids=("e1", "e2"),
                          verified_at=old.isoformat())
    assert state.revision == 1
    assert ledger.authoritative(state.claim) is False
    assert ledger.expired_claims() == (state.claim,)
    refreshed = ledger.record(claim=state.claim, verification_state="verified",
                               verification_attestation_sha256="b" * 64, evidence_record_ids=("e1", "e2"))
    assert refreshed.revision == 2
    assert ledger.authoritative(state.claim) is True


def test_contradiction_resolver_refuses_weighted_majority_truth(tmp_path):
    resolver = ContradictionResolver()
    claim = "Algorithm A decreases measured latency by 10 percent."
    support = EvidenceItem(source_id="a", locator="a", kind=EvidenceKind.PRIMARY_EMPIRICAL, supports=True,
        independence_group="lab-a", quality=1.0, provenance_verified=True, peer_reviewed=True,
        preregistered=True, data_available=True, code_available=True, sample_size=500, uncertainty_reported=True, primary=True)
    oppose = EvidenceItem(source_id="b", locator="b", kind=EvidenceKind.REPLICATION, supports=False,
        independence_group="lab-b", quality=0.6, provenance_verified=True, peer_reviewed=True,
        preregistered=True, data_available=True, code_available=True, sample_size=100, uncertainty_reported=True, primary=True)
    report = resolver.resolve(claim, (support, oppose))
    assert report.state == "contested"
    assert report.methodological_conflict is True
    assert report.support_quality > report.contradiction_quality
    assert "Do not expose" in report.required_actions[0]
    assert resolver.verify(report) is True


def test_retracting_source_revokes_claim_and_removes_orientation_authority(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Algorithm A decreases measured latency by 10 percent."
    record = _promote(engine, claim)
    assert record.claims == (claim,)
    assert engine.truth_ledger.authoritative(claim) is True
    before = engine.orientation_pack("latency research")
    assert claim in before["claims"]

    result = engine.retract_source("study-primary", "measurement calibration was invalid")
    assert claim in result["affected_claims"]
    assert engine.truth_ledger.authoritative(claim) is False
    after = engine.orientation_pack("latency research")
    assert claim not in after["claims"]
    assert any("NON-AUTHORITATIVE" in row and claim in row for row in after["unresolved"])
    historical = engine.fabric.get(record.id)
    assert historical is not None and claim in historical.claims


def test_derivative_source_retraction_cascades_to_dependent_evidence(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "System B decreases measured error rate by 5 percent."
    _promote(engine, claim, derivative=True)
    descendants = engine.source_lineage.descendants("study-primary")
    assert [x.source_id for x in descendants] == ["study-replication"]
    result = engine.retract_source("study-primary", "primary dataset withdrawn")
    assert set(result["affected_sources"]) == {"study-primary", "study-replication"}
    assert len(result["retracted_evidence_records"]) == 2
    assert engine.truth_ledger.authoritative(claim) is False


def test_reverification_can_restore_authority_only_after_valid_evidence_returns(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "System C decreases measured latency by 8 percent."
    _promote(engine, claim)
    engine.retract_source("study-primary", "withdrawn")
    assert engine.truth_ledger.authoritative(claim) is False
    report = engine.reverify_claim(claim)
    assert report["state"] != "verified"
    assert report["authoritative"] is False


def test_jeeves_reasoning_uses_live_truth_projection_not_historical_archive(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "System D decreases measured latency by 11 percent."
    _promote(engine, claim)
    jeeves = KnowledgeAugmentedJeeves(engine)
    before = jeeves.reason({"prompt": "empirical latency research", "_curiosity_signal_key": "before"})
    assert claim in before["known_claims"]

    engine.retract_source("study-primary", "calibration failure")
    after = jeeves.reason({"prompt": "empirical latency research", "_curiosity_signal_key": "after"})
    assert claim not in after["known_claims"]
    assert any("NON-AUTHORITATIVE" in gap and claim in gap for gap in after["unresolved"])
    assert after["epistemic_state"] != "grounded"
