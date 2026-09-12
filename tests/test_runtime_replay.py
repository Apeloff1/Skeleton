from dataclasses import replace

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
    first = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger, pipeline_contract_digest="a" * 64, provenance_digest="b" * 64)
    second = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger, pipeline_contract_digest="a" * 64, provenance_digest="b" * 64)
    assert first == second
    assert replay_digest(first) == replay_digest(second)
    assert first.runtime_digest
    assert first.selected_policy_decision_id == "s1:orient"
    audit = audit_runtime(first, ledger)
    assert audit.valid


def test_runtime_capture_accepts_lifecycle_bound_policy_identity():
    ledger = _ledger()
    ledger.append(session_id="s1", decision_id="s1:practice-later", domain="session_runtime", action="practice", rationale=("later accepted action",), disposition=DecisionDisposition.ACCEPTED, predecessors=("s1:orient",))
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", selected_policy_decision_id="s1:orient", rejected_policies=(), ledger=ledger)
    assert snapshot.selected_policy_decision_id == "s1:orient"
    assert audit_runtime(snapshot, ledger).valid


def test_runtime_capture_rejects_unbound_selected_policy_identity():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", selected_policy_decision_id="s1:forged", rejected_policies=(), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("decision identity is absent from ledger" in item for item in audit.violations)


def test_runtime_audit_detects_runtime_digest_tampering():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", rejected_policies=(), ledger=ledger)
    tampered = replace(snapshot, runtime_digest="f" * 64)
    audit = audit_runtime(tampered, ledger)
    assert not audit.valid
    assert any("runtime-integrity divergence" in item for item in audit.violations)


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
    assert any("does not have a unique ACCEPTED ledger attribution" in item for item in audit.violations)


def test_runtime_audit_rejects_duplicate_accepted_policy_without_identity():
    ledger = _ledger()
    ledger.append(session_id="s1", decision_id="s1:practice-duplicate", domain="session_runtime", action="practice", rationale=("duplicate action",), disposition=DecisionDisposition.ACCEPTED)
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", rejected_policies=(), ledger=ledger)
    assert snapshot.selected_policy_decision_id == ""
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("missing a decision identity" in item for item in audit.violations)


def test_runtime_audit_rejects_noncontiguous_event_sequences():
    ledger = _ledger()
    events = (SessionEvent(1, SessionPhase.INTAKE, "session_opened"), SessionEvent(3, SessionPhase.DIAGNOSE, "control_plan_ready"))
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("event sequence" in item for item in audit.violations)


def test_runtime_audit_rejects_complete_without_terminal_event():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.COMPLETE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", rejected_policies=(), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("without a terminal COMPLETE event" in item for item in audit.violations)


def test_runtime_audit_rejects_events_after_complete():
    ledger = _ledger()
    events = (SessionEvent(1, SessionPhase.INTAKE, "session_opened"), SessionEvent(2, SessionPhase.COMPLETE, "transition:complete"), SessionEvent(3, SessionPhase.COMPLETE, "late_event"))
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.COMPLETE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("events after COMPLETE" in item for item in audit.violations)


def test_runtime_audit_rejects_invalid_provenance_digest():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", rejected_policies=(), ledger=ledger, pipeline_contract_digest="not-a-digest")
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("provenance is incomplete" in item for item in audit.violations)


def test_runtime_audit_rejects_unpaired_valid_provenance():
    ledger = _ledger()
    snapshot = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),), selected_policy="practice", rejected_policies=(), ledger=ledger, pipeline_contract_digest="a" * 64)
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("provenance is incomplete" in item for item in audit.violations)


def test_replay_digest_changes_when_provenance_changes():
    ledger = _ledger()
    events = (SessionEvent(1, SessionPhase.INTAKE, "session_opened"),)
    first = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger, pipeline_contract_digest="a" * 64, provenance_digest="b" * 64)
    second = RuntimeReplaySnapshot.capture(session_id="s1", phase=SessionPhase.DIAGNOSE, events=events, selected_policy="practice", rejected_policies=(), ledger=ledger, pipeline_contract_digest="c" * 64, provenance_digest="b" * 64)
    assert replay_digest(first) != replay_digest(second)
