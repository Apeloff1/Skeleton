from __future__ import annotations
import hashlib
from datetime import datetime, timezone
import pytest
from skeleton.observability.runbooks import Runbook,RunbookError,RunbookRegistry,RunbookStep,RunbookValidation,StepKind,ValidationStatus

SHA=hashlib.sha256(b"drill").hexdigest()

def steps():
    return (
      RunbookStep("STEP.OBSERVE",StepKind.OBSERVE,"Inspect queue depth",signal_ref="SIGNAL.QUEUE.DEPTH",next_step_ids=("STEP.DECIDE",)),
      RunbookStep("STEP.DECIDE",StepKind.DECISION,"Choose recovery or escalation",next_step_ids=("STEP.RECOVER","STEP.ESCALATE")),
      RunbookStep("STEP.RECOVER",StepKind.COMMAND,"Restart bounded worker",command_ref="CMD.WORKER.RESTART",authority_ref="AUTH.OPERATOR.RECOVERY",rollback_step_id="STEP.ROLLBACK",next_step_ids=("STEP.STOP",)),
      RunbookStep("STEP.ROLLBACK",StepKind.ROLLBACK,"Restore previous worker",command_ref="CMD.WORKER.ROLLBACK",authority_ref="AUTH.OPERATOR.RECOVERY",next_step_ids=("STEP.STOP",)),
      RunbookStep("STEP.ESCALATE",StepKind.ESCALATE,"Escalate to incident commander"),
      RunbookStep("STEP.STOP",StepKind.STOP,"Stop automation and preserve evidence"),
    )
def book(version="V1"):return Runbook("RUNBOOK.QUEUE.RECOVERY",version,"sre","read-only diagnostics; no autonomous mutation", "STEP.OBSERVE",steps())

def test_runbook_binds_signals_commands_authority_rollback_and_stop():
    b=book(); assert len(b.digest)==64; assert any(s.kind is StepKind.STOP for s in b.steps)
def test_observe_requires_named_signal():
    with pytest.raises(RunbookError,match="signal_ref"):RunbookStep("STEP.OBS",StepKind.OBSERVE,"look")
def test_command_requires_named_command_and_authority():
    with pytest.raises(RunbookError,match="command_ref and authority_ref"):RunbookStep("STEP.CMD",StepKind.COMMAND,"run",command_ref="CMD.RUN")
def test_terminal_step_cannot_continue():
    with pytest.raises(RunbookError,match="terminal"):RunbookStep("STEP.STOP",StepKind.STOP,"stop",next_step_ids=("STEP.X",))
def test_unknown_successor_rejected():
    s=list(steps()); s[0]=RunbookStep("STEP.OBSERVE",StepKind.OBSERVE,"look",signal_ref="SIGNAL.X",next_step_ids=("STEP.MISSING",))
    with pytest.raises(RunbookError,match="unknown successor"):Runbook("RUNBOOK.X","V1","ops","degraded","STEP.OBSERVE",tuple(s))
def test_unreachable_steps_rejected():
    s=(RunbookStep("STEP.START",StepKind.STOP,"stop"),RunbookStep("STEP.ORPHAN",StepKind.STOP,"orphan"))
    with pytest.raises(RunbookError,match="unreachable"):Runbook("RUNBOOK.X","V1","ops","degraded","STEP.START",s)
def test_runbook_requires_explicit_stop_or_escalation():
    s=(RunbookStep("STEP.START",StepKind.OBSERVE,"look",signal_ref="SIGNAL.X"),)
    with pytest.raises(RunbookError,match="stop or escalation"):Runbook("RUNBOOK.X","V1","ops","degraded","STEP.START",s)
def test_version_identity_is_immutable():
    r=RunbookRegistry(); r.register(book())
    changed=Runbook("RUNBOOK.QUEUE.RECOVERY","V1","different-owner","degraded","STEP.OBSERVE",steps())
    with pytest.raises(RunbookError,match="immutable"):r.register(changed)
def test_drill_must_bind_exact_runbook_digest():
    r=RunbookRegistry(); r.register(book())
    v=RunbookValidation("VALIDATION.1","RUNBOOK.QUEUE.RECOVERY",hashlib.sha256(b"wrong").hexdigest(),"DRILL.1",ValidationStatus.PASSED,SHA)
    with pytest.raises(RunbookError,match="exact runbook"):r.record_validation(v)
def test_passed_drill_validates_only_exact_version():
    r=RunbookRegistry(); one=book("V1"); two=book("V2"); r.register(one);r.register(two)
    r.record_validation(RunbookValidation("VALIDATION.1",one.runbook_id,one.digest,"DRILL.1",ValidationStatus.PASSED,SHA))
    assert r.validated(one.runbook_id,"V1") is True
    assert r.validated(two.runbook_id,"V2") is False
def test_failed_drill_does_not_validate():
    r=RunbookRegistry(); b=book();r.register(b)
    r.record_validation(RunbookValidation("VALIDATION.1",b.runbook_id,b.digest,"DRILL.1",ValidationStatus.FAILED,SHA))
    assert r.validated(b.runbook_id,b.version) is False

def test_rollback_requires_named_command_and_authority():
    with pytest.raises(RunbookError,match="command_ref and authority_ref"):
        RunbookStep("STEP.ROLLBACK",StepKind.ROLLBACK,"restore",command_ref="CMD.RESTORE")

def test_reachable_nonterminating_cycle_is_rejected():
    s=(
      RunbookStep("STEP.START",StepKind.DECISION,"choose",next_step_ids=("STEP.LOOP","STEP.STOP")),
      RunbookStep("STEP.LOOP",StepKind.DECISION,"loop",next_step_ids=("STEP.LOOP",)),
      RunbookStep("STEP.STOP",StepKind.STOP,"stop"),
    )
    with pytest.raises(RunbookError,match="path to stop or escalation"):
        Runbook("RUNBOOK.LOOP","V1","ops","degraded","STEP.START",s)

def test_cycle_with_exit_to_terminal_is_allowed():
    s=(
      RunbookStep("STEP.START",StepKind.DECISION,"choose",next_step_ids=("STEP.LOOP",)),
      RunbookStep("STEP.LOOP",StepKind.DECISION,"retry or stop",next_step_ids=("STEP.LOOP","STEP.STOP")),
      RunbookStep("STEP.STOP",StepKind.STOP,"stop"),
    )
    assert Runbook("RUNBOOK.RETRY","V1","ops","degraded","STEP.START",s).entry_step_id=="STEP.START"

def test_validation_status_cannot_be_free_form():
    b=book()
    with pytest.raises(RunbookError,match="ValidationStatus"):
        RunbookValidation("VALIDATION.BAD",b.runbook_id,b.digest,"DRILL.BAD","passed",SHA)

def test_drill_observation_time_is_normalized_and_precise():
    b=book()
    receipt=RunbookValidation("VALIDATION.TIME",b.runbook_id,b.digest,"DRILL.TIME",ValidationStatus.PASSED,SHA,datetime(2026,10,5,15,0,tzinfo=timezone.utc))
    assert receipt.observed_at.tzinfo is timezone.utc
    with pytest.raises(RunbookError,match="whole-second"):
        RunbookValidation("VALIDATION.SUBSECOND",b.runbook_id,b.digest,"DRILL.SUBSECOND",ValidationStatus.PASSED,SHA,datetime(2026,10,5,15,0,0,1,tzinfo=timezone.utc))

def test_duplicate_drill_receipt_for_exact_runbook_is_rejected():
    r=RunbookRegistry(); b=book(); r.register(b)
    r.record_validation(RunbookValidation("VALIDATION.A",b.runbook_id,b.digest,"DRILL.SAME",ValidationStatus.PASSED,SHA))
    with pytest.raises(RunbookError,match="drill identity"):
        r.record_validation(RunbookValidation("VALIDATION.B",b.runbook_id,b.digest,"DRILL.SAME",ValidationStatus.FAILED,SHA))
