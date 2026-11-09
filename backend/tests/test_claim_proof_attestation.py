from dataclasses import replace

from core.claim_proof import build_claim_proof, verify_claim_proof
from core.epistemic_attestation import attest_epistemic_state, verify_epistemic_root
from core.verified_curiosity import VerifiedCuriosityEngine


def _row(source, group, claim, *, replication=False):
    return {
        "source_id": source,
        "source": source,
        "locator": f"doi:{source}#result",
        "kind": "replication" if replication else "primary_empirical",
        "supports": True,
        "independence_group": group,
        "quality": 1.0,
        "reproducible": replication,
        "peer_reviewed": True,
        "primary": True,
        "provenance_verified": True,
        "preregistered": True,
        "data_available": True,
        "code_available": True,
        "sample_size": 600,
        "uncertainty_reported": True,
        "citation_binding": {
            "binding_method": "direct_quote",
            "evidence_span": claim,
            "mapping_rationale": "Exact claim text is reported as the measured result.",
        },
    }


def _promote(engine, claim):
    engine.observe_prompt("empirical claim proof")
    inquiry = engine.next_inquiry(); assert inquiry is not None
    record = engine.accept_finding(inquiry, {
        "title": "Proof-grade empirical result",
        "summary": "Independent primary and replication evidence.",
        "claims": [claim],
        "falsifiable": {claim: True},
        "claim_evidence": {claim: [
            _row("proof-primary", "proof-lab-a", claim),
            _row("proof-replication", "proof-lab-b", claim, replication=True),
        ]},
    })
    assert record.claims == (claim,)
    return record


def test_epistemic_root_is_deterministic_and_tamper_evident(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    first = attest_epistemic_state(engine.verification_status())
    second = attest_epistemic_state(engine.verification_status())
    assert first == second
    assert verify_epistemic_root(first) is True
    assert verify_epistemic_root(replace(first, root_sha256="0" * 64)) is False
    assert len(first.components) == 6


def test_authoritative_claim_emits_offline_verifiable_proof(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Protocol A decreases measured tail latency by 14 percent."
    _promote(engine, claim)

    proof = build_claim_proof(engine, claim, generated_at="2026-09-14T15:00:00+00:00")
    assert proof.authoritative is True
    assert proof.reasons == ()
    assert len(proof.evidence) == 2
    assert all(row["citation_bound"] for row in proof.evidence)
    assert proof.independence["effective_independent_sources"] == 2
    assert proof.epistemic_root["root_sha256"]
    assert verify_claim_proof(proof) is True

    assert verify_claim_proof(replace(proof, authoritative=False)) is False
    assert verify_claim_proof(replace(proof, attestation_sha256="f" * 64)) is False


def test_retraction_rotates_root_and_produces_verifiable_negative_proof(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Protocol B decreases measured error rate by 9 percent."
    _promote(engine, claim)
    before = build_claim_proof(engine, claim, generated_at="2026-09-14T15:00:00+00:00")
    assert before.authoritative is True

    engine.retract_source("proof-primary", "publisher retracted invalid calibration")
    after = build_claim_proof(engine, claim, generated_at="2026-09-14T15:01:00+00:00")
    assert after.authoritative is False
    assert verify_claim_proof(after) is True
    assert after.epistemic_root["root_sha256"] != before.epistemic_root["root_sha256"]
    assert any(row["retracted"] for row in after.evidence)


def test_calibration_rotates_epistemic_root_but_never_promotes_truth(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Unverified design C decreases measured cost by 5 percent."
    before = attest_epistemic_state(engine.verification_status())
    assert engine.truth_ledger.authoritative(claim) is False

    engine.record_forecast(claim=claim, probability=0.93, forecaster="planner", forecast_id="cal-1")
    after = attest_epistemic_state(engine.verification_status())
    assert after.root_sha256 != before.root_sha256
    assert engine.truth_ledger.authoritative(claim) is False
    assert engine.calibration.metrics()["resolved"] == 0


def test_unknown_claim_has_verifiable_negative_proof_instead_of_fake_certainty(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    proof = build_claim_proof(engine, "Unknown system produces measured gain.", generated_at="2026-09-14T15:00:00+00:00")
    assert proof.authoritative is False
    assert "no_truth_state" in proof.reasons
    assert "no_active_claim_bound_evidence" in proof.reasons
    assert verify_claim_proof(proof) is True
