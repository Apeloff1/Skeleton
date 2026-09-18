"""Pure dry-run admission reports for shell commands and plans."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.admission import AdmissionRequest,AdmissionDecision,ShellAdmission
from skeleton.shells.execution_plan import ExecutionPlan
from skeleton.shells.runner import ShellCommand

@dataclass(frozen=True)
class DryRunStep:
    step_id:str
    allowed:bool
    code:str
    message:str

    def to_dict(self)->dict[str,object]:
        return {
            "step_id":self.step_id,
            "allowed":self.allowed,
            "code":self.code,
            "message":self.message,
        }

@dataclass(frozen=True)
class DryRunReport:
    steps:tuple[DryRunStep,...]

    @property
    def allowed(self)->bool:
        return all(step.allowed for step in self.steps)

    def to_dict(self)->dict[str,object]:
        return {"allowed":self.allowed,"steps":[step.to_dict() for step in self.steps]}

class ShellDryRun:
    """Invoke admission only. Never calls ShellRunner or ShellExecutor."""

    def __init__(self,admission:ShellAdmission)->None:
        self.admission=admission

    def command(self,request:AdmissionRequest)->DryRunReport:
        decision=self.admission.evaluate(request)
        return DryRunReport((
            DryRunStep(
                "command",
                decision.allowed,
                decision.code,
                decision.message,
            ),
        ))

    def plan(self,plan:ExecutionPlan,request_factory)->DryRunReport:
        steps=[]
        for step in plan.topological_order():
            request=request_factory(step)
            if not isinstance(request,AdmissionRequest):
                raise TypeError("request_factory must return AdmissionRequest")
            decision=self.admission.evaluate(request)
            steps.append(DryRunStep(step.step_id,decision.allowed,decision.code,decision.message))
        return DryRunReport(tuple(steps))
