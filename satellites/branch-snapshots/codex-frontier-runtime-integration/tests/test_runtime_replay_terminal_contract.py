from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.runtime_replay import RuntimeReplaySnapshot, audit_runtime
from skeleton.school.session_runtime import SessionEvent, SessionPhase


def _ledger():
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
    return ledger


def test_complete_snapshot_requires_terminal_complete_event():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.COMPLETE,
        events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),),
        selected_policy="practice",
        rejected_policies=(),
        ledger=ledger,
    )
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("without a terminal COMPLETE event" in item for item in audit.violations)


def test_events_after_complete_are_rejected():
    ledger = _ledger()
    events = (
        SessionEvent(1, SessionPhase.INTAKE, "session_opened"),
        SessionEvent(2, SessionPhase.COMPLETE, "session_complete"),
        SessionEvent(3, SessionPhase.COMPLETE, "late_event"),
    )
    snapshot = RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.COMPLETE,
        events=events,
        selected_policy="practice",
        rejected_policies=(),
        ledger=ledger,
    )
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("events after COMPLETE" in item for item in audit.violations)


def test_rejected_policy_requires_explicit_rejection_record():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.DIAGNOSE,
        events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),),
        selected_policy="practice",
        rejected_policies=("challenge",),
        ledger=ledger,
    )
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("lacks a REJECTED ledger record" in item for item in audit.violations)


def test_causal_predecessor_must_be_earlier_than_decision():
    ledger = _ledger()
    ledger.append(
        session_id="s1",
        decision_id="d2",
        domain="runtime",
        action="challenge",
        predecessors=("d1",),
        disposition=DecisionDisposition.ACCEPTED,
    )
    # Corrupt the causal relation while retaining the existing hash chain so
    # the runtime audit must independently detect the semantic impossibility.
    record = ledger.records[1]
    ledger.records[1] = record.__class__(**{**record.__dict__, "predecessors": ("d2",)})
    snapshot = RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.DIAGNOSE,
        events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),),
        selected_policy="practice",
        rejected_policies=(),
        ledger=ledger,
    )
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("non-causal predecessor" in item for item in audit.violations)
