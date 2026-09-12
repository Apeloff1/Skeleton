from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.runtime_replay import RuntimeReplaySnapshot, audit_runtime, replay_digest
from skeleton.school.session_runtime import SessionEvent, SessionPhase


def _ledger(session="s1"):
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "skill", "observed", 1.0, "test"))
    ledger.append(session_id=session, decision_id=f"{session}:orient", domain="session_runtime", action="practice", rationale=("test",), evidence=("e1",), disposition=DecisionDisposition.ACCEPTED)
    return ledger


def test_runtime_snapshot_is_deterministic_and_auditable():
    ledger = _ledger()
    events = (SessionEvent(1, SessionPhase.INTAKE, "session_opened", (("session_id", "s1"),)),)
    first = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger)
    second = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger)
    assert first == second
    assert replay_digest(first) == replay_digest(second)
    assert first.runtime_digest
    audit = audit_runtime(first, ledger)
    assert audit.valid


def test_runtime_audit_detects_ledger_tampering():
    ledger = _ledger()
    events = (SessionEvent(1, SessionPhase.INTAKE, "session_opened"),)
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger)
    record = ledger.records[0]
    ledger.records[0] = record.__class__(**{**record.__dict__, "action": "challenge"})
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("ledger integrity" in item for item in audit.violations)


def test_runtime_audit_rejects_a_policy_claimed_as_rejected_but_accepted():
    ledger = _ledger()
    ledger.append(session_id="s1", decision_id="s1:challenge", domain="session_runtime", action="challenge", rationale=("candidate",), disposition=DecisionDisposition.ACCEPTED)
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", rejected_policies=("challenge",), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("lacks a REJECTED ledger record" in item for item in audit.violations)


def test_runtime_audit_rejects_selected_policy_marked_rejected():
    ledger = _ledger()
    ledger.append(session_id="s1", decision_id="s1:alternative", domain="session_runtime", action="challenge", rationale=("counterfactual alternative", "not executed"), disposition=DecisionDisposition.REJECTED)
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="challenge", rejected_policies=("challenge",), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("incorrectly recorded as rejected" in item for item in audit.violations)


def test_runtime_audit_rejects_noncontiguous_event_sequences():
    ledger = _ledger()
    events = (
        SessionEvent(1, SessionPhase.INTAKE, "session_opened"),
        SessionEvent(3, SessionPhase.DIAGNOSE, "control_plan_ready"),
    )
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("event sequence" in item for item in audit.violations)
