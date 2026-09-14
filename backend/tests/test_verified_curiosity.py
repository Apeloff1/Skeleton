from core.truth_verifier import EvidenceItem, EvidenceKind
from core.verified_curiosity import VerifiedCuriosityEngine


def _verified_evidence(source, group, claim, *, replication=False, supports=True, quality=0.95):
    return {
        "source_id": source,
        "source": source,
        "locator": "result:1",
        "kind": "replication" if replication else "primary_empirical",
        "independence_group": group,
        "quality": quality,
        "supports": supports,
        "reproducible": replication,
        "peer_reviewed": True,
        "primary": True,
        "provenance_verified": True,
        "preregistered": True,
        "data_available": True,
        "code_available": True,
        "sample_size": 240,
        "uncertainty_reported": True,
        "citation_binding": {
            "binding_method": "direct_quote",
            "evidence_span": claim,
            "mapping_rationale": "",
        },
    }


def test_only_verified_claims_enter_authoritative_orientation(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    engine.observe_prompt("clinical recovery measurement")
    inquiry = engine.next_inquiry()
    assert inquiry is not None
    verified = "Treatment A decreases measured recovery time by 12 percent."
    speculation = "Invisible energy probably explains all recovery."
    record = engine.accept_finding(inquiry, {
        "title": "Recovery study",
        "summary": "A mixed research synthesis.",
        "claims": [verified, speculation],
        "falsifiable": {verified: True, speculation: False},
        "claim_evidence": {
            verified: [
                _verified_evidence("study-a", "lab-a", verified),
                _verified_evidence("study-b", "lab-b", verified, replication=True),
            ],
            speculation: [],
        },
        "questions": ["Does the effect generalize?"],
    })
    assert record.claims == (verified,)
    assert speculation not in record.summary
    assert any("IRRELEVANT SPECULATION" in gap for gap in record.questions)
    pack = engine.orientation_pack("recovery measurement")
    assert verified in pack["claims"]
    assert speculation not in pack["claims"]
    assert pack["confidence_floor"] > 0


def test_model_only_research_creates_gap_not_verified_fact(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    engine.observe_prompt("fusion reactor claim")
    inquiry = engine.next_inquiry()
    assert inquiry is not None
    claim = "Fusion device X produces net-positive measured energy."
    record = engine.accept_finding(inquiry, {
        "summary": "Three models guessed the same thing.",
        "claims": [claim],
        "claim_evidence": {claim: [
            {"source": "model-observation:a", "kind": "model_observation", "independence_group": "model-a", "quality": 1.0},
            {"source": "model-observation:b", "kind": "model_observation", "independence_group": "model-b", "quality": 1.0},
            {"source": "model-observation:c", "kind": "model_observation", "independence_group": "model-c", "quality": 1.0},
        ]},
        "falsifiable": {claim: True},
    })
    assert record.claims == ()
    assert record.confidence == 0.0
    assert record.summary.startswith("No claim")
    assert any("IRRELEVANT SPECULATION" in x for x in record.questions)


def test_contradicted_claim_is_quarantined_from_orientation(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    engine.observe_prompt("algorithm benchmark")
    inquiry = engine.next_inquiry()
    assert inquiry is not None
    claim = "Algorithm A decreases measured latency."
    record = engine.accept_finding(inquiry, {
        "summary": "Conflicting benchmark evidence.",
        "claims": [claim],
        "falsifiable": {claim: True},
        "claim_evidence": {claim: [
            _verified_evidence("bench-a", "lab-a", claim),
            _verified_evidence("bench-b", "lab-b", claim, replication=True),
            _verified_evidence("bench-c", "lab-c", claim, supports=False, replication=True),
        ]},
    })
    assert claim not in record.claims
    assert any("CONTRADICTED" in x for x in record.questions)
    assert any("CONTRADICTION" in x for x in record.contradictions)


def test_retracted_evidence_no_longer_counts(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Measured output is 10 units."
    record = engine.evidence_registry.register(claim, EvidenceItem(
        source_id="study-a",
        locator="r1",
        kind=EvidenceKind.PRIMARY_EMPIRICAL,
        supports=True,
        independence_group="lab-a",
        quality=0.95,
        reproducible=True,
        peer_reviewed=True,
        primary=True,
        provenance_verified=True,
        preregistered=True,
        data_available=True,
        code_available=True,
        sample_size=100,
        uncertainty_reported=True,
    ))
    assert engine.evidence_registry.retract(record.id, "paper withdrawn") is True
    assert engine.evidence_registry.evidence_for(claim) == ()
    records = engine.evidence_registry.records_for(claim)
    assert records[0].retracted is True


def test_truth_gate_status_is_explicit(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    status = engine.verification_status()
    assert status["truth_gated"] is True
    assert status["speculation_authoritative"] is False
    assert status["model_consensus_is_empirical_evidence"] is False
    assert status["semantic_similarity_is_truth_identity"] is False
    assert status["calibration"]["cross_process_locking"] is True
    assert status["verification_policy"]["minimum_independent_support"] == 2
    assert status["verification_policy"]["require_provenance_verified"] is True
    assert status["verification_policy"]["require_independent_replication_for_experiments"] is True
