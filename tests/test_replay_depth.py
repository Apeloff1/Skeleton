from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.replay import JeevesReplay, ReplaySnapshot, replay_digest


def _ledger(action: str, *, evidence: str = "e1", rejected: bool = False) -> DecisionLedger:
    ledger = DecisionLedger()
    from skeleton.school.decision_ledger import EvidenceKind, EvidenceRef

    ledger.register_evidence(EvidenceRef(evidence, EvidenceKind.OBSERVATION, "skill", "evidence"))
    ledger.append(
        session_id="s1",
        decision_id="d1",
        domain="test",
        action=action,
        evidence=(evidence,),
        state={"mastery": 0.5},
        policy={"selected": action},
        disposition=DecisionDisposition.REJECTED if rejected else DecisionDisposition.ACCEPTED,
    )
    return ledger


def test_replay_detects_policy_and_evidence_divergence() -> None:
    left = _ledger("practice")
    right = _ledger("practice", evidence="e1")
    assert JeevesReplay().compare_actions(left.records, right.records).identical

    right.records[0] = right.records[0].__class__(
        **{**right.records[0].__dict__, "policy_digest": "tampered"}
    )
    report = JeevesReplay().compare_actions(left.records, right.records)
    assert any(m.reason == "policy-state divergence" for m in report.mismatches)


def test_replay_snapshot_separates_selected_and_rejected_policies() -> None:
    ledger = _ledger("practice")
    rejected = ledger.append(
        session_id="s1",
        decision_id="d2",
        domain="test",
        action="challenge",
        evidence=("e1",),
        policy={"selected": "practice"},
        predecessors=("d1",),
        disposition=DecisionDisposition.REJECTED,
    )
    snapshot = ReplaySnapshot.from_records(ledger.records)
    assert snapshot.selected_actions == ("practice",)
    assert snapshot.rejected_actions == ("challenge",)
    assert snapshot.decision_ids == ("d1", "d2")
    assert snapshot.predecessors == ((), ("d1",))
    assert snapshot.record_hashes == (ledger.records[0].record_hash, ledger.records[1].record_hash)
    assert snapshot.evidence_ids == ("e1", "e1")
    assert replay_digest(ledger.records) == replay_digest(ledger.records)
    assert rejected.disposition is DecisionDisposition.REJECTED


def test_replay_detects_causal_or_integrity_divergence() -> None:
    left = _ledger("practice")
    right = _ledger("practice")
    right.records[0] = right.records[0].__class__(
        **{**right.records[0].__dict__, "record_hash": "tampered"}
    )
    report = JeevesReplay().compare_actions(left.records, right.records)
    assert any(m.reason == "record-integrity divergence" for m in report.mismatches)
