from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.session_audit import audit_session


def test_session_audit_tracks_first_class_supersession_lineage():
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "skill", "observed"))
    ledger.append(
        session_id="s1",
        decision_id="d1",
        domain="runtime",
        action="practice",
        evidence=("e1",),
        disposition=DecisionDisposition.ACCEPTED,
    )
    replacement = ledger.supersede("d1", replacement_id="d2")
    assert replacement.supersedes == "d1"
    audit = audit_session(ledger, "s1")
    assert audit.valid
    assert "active-record-filter" in audit.checks
    assert "supersession-audit" in audit.checks


def test_session_audit_detects_duplicate_supersession_target():
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "skill", "observed"))
    ledger.append(session_id="s1", decision_id="d1", domain="runtime", action="practice", evidence=("e1",), disposition=DecisionDisposition.ACCEPTED)
    ledger.supersede("d1", replacement_id="d2")
    target = ledger.records[0]
    ledger.records.append(
        target.__class__(
            sequence=3,
            decision_id="d3",
            session_id="s1",
            domain="runtime",
            action="practice",
            rationale=(),
            evidence=("e1",),
            predecessors=("d1",),
            state_digest="",
            policy_digest="",
            disposition=DecisionDisposition.ACCEPTED,
            supersedes="d1",
            record_hash="tampered",
        )
    )
    audit = audit_session(ledger, "s1")
    assert not audit.valid
    assert any("superseded more than once" in item for item in audit.failures)
