from dataclasses import replace
from datetime import UTC, datetime, timedelta

from core.epistemic_transparency import EpistemicTransparency
from core.portable_claim_proof import build_portable_claim_proof, verify_portable_claim_proof
from core.transparency_finality import TransparencyFinality
from core.transparency_gossip import TransparencyGossip
from core.transparency_witness import TransparencyWitnessLedger, TrustedWitness
from core.verified_curiosity import VerifiedCuriosityEngine


def _row(source, group, claim, *, replication=False):
    return {
        "source_id": source, "source": source, "locator": f"doi:{source}#result",
        "kind": "replication" if replication else "primary_empirical",
        "supports": True, "independence_group": group, "quality": 1.0,
        "reproducible": replication, "peer_reviewed": True, "primary": True,
        "provenance_verified": True, "preregistered": True, "data_available": True,
        "code_available": True, "sample_size": 800, "uncertainty_reported": True,
        "citation_binding": {
            "binding_method": "direct_quote", "evidence_span": claim,
            "mapping_rationale": "Exact measured result.",
        },
    }


def _promote(engine, claim):
    engine.observe_prompt("quorum finality empirical benchmark")
    inquiry = engine.next_inquiry(); assert inquiry is not None
    record = engine.accept_finding(inquiry, {
        "summary": "Independent primary and replication measurements.",
        "claims": [claim], "falsifiable": {claim: True},
        "claim_evidence": {claim: [
            _row("final-primary", "lab-a", claim),
            _row("final-replication", "lab-b", claim, replication=True),
        ]},
    })
    assert record.claims == (claim,)


def _finality_stack(tmp_path):
    transparency = EpistemicTransparency(tmp_path / "transparency")
    gossip = TransparencyGossip(tmp_path / "gossip")
    witnesses = TransparencyWitnessLedger(
        tmp_path / "witnesses",
        trusted_witnesses=(
            TrustedWitness("w1", "org-a"),
            TrustedWitness("w2", "org-b"),
            TrustedWitness("w3", "org-c"),
        ),
        required_groups=3,
    )
    finality = TransparencyFinality(tmp_path / "finality", transparency=transparency, gossip=gossip, witnesses=witnesses)
    return transparency, gossip, witnesses, finality


def test_published_packet_fails_when_quorum_finality_is_required(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol Q decreases measured tail latency by 11 percent."
    _promote(engine, claim)
    transparency, _, _, finality = _finality_stack(tmp_path)
    now = datetime(2026, 9, 14, 16, 50, tzinfo=UTC)
    packet = build_portable_claim_proof(engine, claim, transparency=transparency, finality=finality,
                                        generated_at=now.isoformat())
    assert packet.transparency_anchor is not None
    assert packet.finality_anchor is None
    assert verify_portable_claim_proof(packet, now=now + timedelta(seconds=1), require_transparency=True) is True
    assert verify_portable_claim_proof(packet, now=now + timedelta(seconds=1), require_finality=True) is False


def test_quorum_finalized_packet_verifies_against_pinned_finality_hash(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol F decreases measured error rate by 12 percent."
    _promote(engine, claim)
    transparency, _, witnesses, finality = _finality_stack(tmp_path)
    now = datetime(2026, 9, 14, 16, 55, tzinfo=UTC)

    provisional = build_portable_claim_proof(engine, claim, transparency=transparency,
                                              generated_at=now.isoformat())
    descriptor = provisional.transparency_anchor["descriptor"]
    for witness_id in ("w1", "w2", "w3"):
        witnesses.observe(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                          root_sha256=descriptor["root_sha256"], witness_id=witness_id,
                          transport_authenticated=True)
    finalized = finality.finalize(finalized_at=(now + timedelta(seconds=1)).isoformat())

    packet = build_portable_claim_proof(engine, claim, transparency=transparency, finality=finality,
                                        generated_at=(now + timedelta(seconds=2)).isoformat())
    assert packet.finality_anchor is not None
    assert packet.finality_anchor["sha256"] == finalized.sha256
    assert verify_portable_claim_proof(
        packet, now=now + timedelta(seconds=3), require_transparency=True, require_finality=True,
        expected_transparency_root=descriptor["root_sha256"], expected_finality_sha256=finalized.sha256,
    ) is True

    wrong = "0" * 64 if finalized.sha256 != "0" * 64 else "f" * 64
    assert verify_portable_claim_proof(packet, now=now + timedelta(seconds=3),
                                       expected_finality_sha256=wrong) is False


def test_substituted_finality_root_fails_even_when_packet_is_rehashed_elsewhere(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol Z decreases measured jitter by 8 percent."
    _promote(engine, claim)
    transparency, _, witnesses, finality = _finality_stack(tmp_path)
    now = datetime.now(UTC)
    provisional = build_portable_claim_proof(engine, claim, transparency=transparency, generated_at=now.isoformat())
    descriptor = provisional.transparency_anchor["descriptor"]
    for witness_id in ("w1", "w2", "w3"):
        witnesses.observe(log_id=descriptor["log_id"], tree_size=descriptor["tree_size"],
                          root_sha256=descriptor["root_sha256"], witness_id=witness_id,
                          transport_authenticated=True)
    finality.finalize()
    packet = build_portable_claim_proof(engine, claim, transparency=transparency, finality=finality)

    altered = dict(packet.finality_anchor); altered["root_sha256"] = "f" * 64
    tampered = replace(packet, finality_anchor=altered)
    assert verify_portable_claim_proof(tampered, now=datetime.now(UTC), require_finality=True) is False
