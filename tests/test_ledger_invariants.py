import pytest
from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef


def ledger():
    l = DecisionLedger()
    l.register_evidence(EvidenceRef("e", EvidenceKind.OBSERVATION, "s", "x"))
    l.append(session_id="s", decision_id="d1", domain="test", action="practice", evidence=("e",))
    return l


def test_supersession_is_single_use_and_filters_active_records():
    l = ledger()
    replacement = l.supersede("d1", replacement_id="d2")
    assert replacement.disposition is DecisionDisposition.ACCEPTED
    assert tuple(r.decision_id for r in l.active_records("s")) == ("d2",)
    with pytest.raises(ValueError, match="already superseded"):
        l.supersede("d1", replacement_id="d3")


def test_self_supersession_is_rejected():
    l = ledger()
    with pytest.raises(ValueError, match="cannot supersede itself"):
        l.supersede("d1", replacement_id="d1")


def test_supersession_replacement_id_must_be_unique():
    l = ledger()
    l.supersede("d1", replacement_id="d2")
    with pytest.raises(ValueError, match="duplicate decision id"):
        l.supersede("d2", replacement_id="d2")


def test_supersession_is_hash_chained_and_explainable():
    l = ledger()
    l.supersede("d1", replacement_id="d2")
    l.verify()
    assert l.records[-1].disposition is DecisionDisposition.ACCEPTED
    assert tuple(r.decision_id for r in l.explain("d2")) == ("d1", "d2")


def test_append_rejects_future_predecessor_reference():
    l = ledger()
    l.records.append(
        l.records[0].__class__(
            sequence=2,
            decision_id="future",
            session_id="s",
            domain="test",
            action="practice",
            predecessors=("d1",),
            record_hash="tampered",
        )
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        l.verify()


def test_verify_rejects_forward_causal_reference_even_with_a_valid_hash():
    l = ledger()
    # A maliciously reconstructed record may name a later decision as its predecessor.
    later = l.records[0].__class__(
        sequence=1,
        decision_id="d0",
        session_id="s",
        domain="test",
        action="practice",
        predecessors=("d1",),
        record_hash="",
    )
    payload = {
        "sequence": later.sequence,
        "decision_id": later.decision_id,
        "session_id": later.session_id,
        "domain": later.domain,
        "action": later.action,
        "rationale": later.rationale,
        "evidence": later.evidence,
        "predecessors": later.predecessors,
        "state_digest": later.state_digest,
        "policy_digest": later.policy_digest,
        "disposition": later.disposition.value,
        "supersedes": later.supersedes,
        "previous": "GENESIS",
    }
    import hashlib
    import json
    hashed = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    l.records[0] = later.__class__(**{**later.__dict__, "record_hash": hashed})
    with pytest.raises(ValueError, match="unknown predecessor"):
        l.verify()
