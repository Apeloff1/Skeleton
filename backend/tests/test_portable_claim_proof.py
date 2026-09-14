from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json

import pytest

from core.epistemic_checkpoint import EpistemicCheckpointIntegrityError, EpistemicCheckpointLedger
from core.epistemic_claim_index import EpistemicClaimIndex
from core.portable_claim_proof import build_portable_claim_proof, verify_portable_claim_proof
from core.sparse_merkle import build_sparse_proof, sparse_merkle_root, verify_sparse_proof
from core.verified_curiosity import VerifiedCuriosityEngine


def _row(source, group, claim, *, replication=False):
    return {
        "source_id": source, "source": source, "locator": f"doi:{source}#result",
        "kind": "replication" if replication else "primary_empirical",
        "supports": True, "independence_group": group, "quality": 1.0,
        "reproducible": replication, "peer_reviewed": True, "primary": True,
        "provenance_verified": True, "preregistered": True, "data_available": True,
        "code_available": True, "sample_size": 700, "uncertainty_reported": True,
        "citation_binding": {
            "binding_method": "direct_quote", "evidence_span": claim,
            "mapping_rationale": "Exact measured result.",
        },
    }


def _promote(engine, claim):
    engine.observe_prompt("portable proof empirical benchmark")
    inquiry = engine.next_inquiry(); assert inquiry is not None
    record = engine.accept_finding(inquiry, {
        "summary": "Independent primary and replication measurements.",
        "claims": [claim], "falsifiable": {claim: True},
        "claim_evidence": {claim: [
            _row("portable-primary", "portable-lab-a", claim),
            _row("portable-replication", "portable-lab-b", claim, replication=True),
        ]},
    })
    assert record.claims == (claim,)


def test_sparse_merkle_verifies_membership_and_nonmembership():
    values = {"Claim A": {"authoritative": True}, "Claim B": {"authoritative": False}}
    root = sparse_merkle_root(values)
    member = build_sparse_proof(values, "Claim A")
    absent = build_sparse_proof(values, "Claim C")
    assert member.root_sha256 == root and member.present is True
    assert absent.root_sha256 == root and absent.present is False
    assert verify_sparse_proof(member) is True
    assert verify_sparse_proof(absent) is True
    assert verify_sparse_proof(replace(member, value={"authoritative": False})) is False


def test_claim_index_rotates_when_authority_state_changes(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Protocol M decreases measured tail latency by 15 percent."
    _promote(engine, claim)
    index = EpistemicClaimIndex(engine)
    before = index.root_sha256()
    proof = index.proof(claim)
    assert proof["present"] is True
    assert proof["value"]["authoritative"] is True

    engine.retract_source("portable-primary", "publisher invalidated calibration")
    after = index.root_sha256()
    assert after != before
    assert index.proof(claim)["value"]["authoritative"] is False


def test_portable_proof_requires_external_root_for_independent_trust(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path / "engine")
    claim = "Protocol P decreases measured error rate by 13 percent."
    _promote(engine, claim)
    checkpoint_ledger = EpistemicCheckpointLedger(tmp_path / "checkpoints")
    issued = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
    packet = build_portable_claim_proof(
        engine, claim, checkpoint_ledger=checkpoint_ledger,
        generated_at=issued.isoformat(), max_age_seconds=900,
    )
    assert packet.authority_proof["present"] is True
    assert packet.checkpoint is not None
    assert verify_portable_claim_proof(packet, now=issued + timedelta(minutes=1)) is True
    assert verify_portable_claim_proof(
        packet, now=issued + timedelta(minutes=1),
        expected_authority_root=packet.authority_root_sha256,
        expected_checkpoint_sha256=packet.checkpoint["sha256"], require_checkpoint=True,
    ) is True
    assert verify_portable_claim_proof(
        packet, now=issued + timedelta(minutes=1), expected_authority_root="0" * 64,
    ) is False
    assert verify_portable_claim_proof(
        packet, now=issued + timedelta(minutes=1), expected_checkpoint_sha256="f" * 64,
    ) is False


def test_portable_absence_proof_and_expiry_fail_closed(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Unknown machine yields measured superlinear energy."
    issued = datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
    packet = build_portable_claim_proof(engine, claim, generated_at=issued.isoformat(), max_age_seconds=60)
    assert packet.authority_proof["present"] is False
    assert packet.claim_proof["authoritative"] is False
    assert verify_portable_claim_proof(packet, now=issued + timedelta(seconds=59)) is True
    assert verify_portable_claim_proof(packet, now=issued + timedelta(seconds=61)) is False


def test_retraction_emits_bound_revocation_witness(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "Protocol R decreases measured latency by 6 percent."
    _promote(engine, claim)
    engine.retract_source("portable-primary", "source formally retracted")
    now = datetime.now(UTC)
    packet = build_portable_claim_proof(engine, claim, generated_at=now.isoformat())
    assert packet.claim_proof["authoritative"] is False
    assert len(packet.revocation_witness_sha256) == 64
    assert verify_portable_claim_proof(packet, now=now + timedelta(seconds=1)) is True
    assert verify_portable_claim_proof(replace(packet, revocation_witness_sha256="0" * 64), now=now) is False


def test_checkpoint_ledger_detects_tampering_and_preserves_monotonic_chain(tmp_path):
    ledger = EpistemicCheckpointLedger(tmp_path)
    first = ledger.record(authority_root_sha256="1" * 64, epistemic_root_sha256="2" * 64,
                          observed_at="2026-09-14T16:00:00+00:00")
    second = ledger.record(authority_root_sha256="3" * 64, epistemic_root_sha256="4" * 64,
                           observed_at="2026-09-14T16:01:00+00:00")
    assert first.sequence == 1 and second.sequence == 2
    assert second.previous_sha256 == first.sha256
    assert ledger.health()["head_sha256"] == second.sha256

    rows = ledger.path.read_text(encoding="utf-8").splitlines()
    corrupt = json.loads(rows[0]); corrupt["authority_root_sha256"] = "9" * 64
    rows[0] = json.dumps(corrupt, sort_keys=True, separators=(",", ":"))
    ledger.path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(EpistemicCheckpointIntegrityError):
        EpistemicCheckpointLedger(tmp_path)
