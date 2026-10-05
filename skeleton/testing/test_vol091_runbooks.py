from __future__ import annotations
import hashlib
import pytest
from skeleton.observability.runbooks import Runbook,RunbookError,RunbookRegistry,RunbookStep,RunbookValidation,StepKind,ValidationStatus

SHA=hashlib.sha256(b"drill").hexdigest()

def steps():
    return (
      RunbookStep("STEP.OBSERVE",StepKind.OBSERVE,"Inspect queue depth",signal_ref="SIGNAL.QUEUE.DEPTH",next_step_ids=("STEP.DECIDE",)),
      RunbookStep("STEP.DECIDE",StepKind.DECISION,"Choose recovery or escalation",next_step_ids=("STEP.RECOVER","STEP.ESCALATE")),
      RunbookStep("STEP.RECOVER",StepKind.COMMAND,"Restart bounded worker",command_ref="CMD.WORKER.RESTART",authority_ref="AUTH.OPERATOR.RECOVERY",rollback_step_id="STEP.ROLLBACK",next_step_ids=("STEP.STOP",)),
      RunbookStep("STEP.ROLLBACK",StepKind.ROLLBACK,"Restore previous worker",command_ref="CMD.WORKER.ROLLBACK",next_step_ids=("STEP.STOP",)),
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
