"""Pure dry-run admission reports for shell commands and plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from skeleton.shells.admission import CommandAdmission
from skeleton.shells.capabilities import CapabilityGrant
from skeleton.shells.execution_plan import ExecutionPlan,PlanStep
from skeleton.shells.runner import ShellCommand

@dataclass(frozen=True)
class DryRunStep:
    step_id:str
    allowed:bool
    command:str
    reason:str

    def to_dict(self)->dict[str,object]:
        return {
            "step_id":self.step_id,
            "allowed":self.allowed,
            "command":self.command,
            "reason":self.reason,
        }

@dataclass(frozen=True)
class DryRunReport:
    steps:tuple[DryRunStep,...]

    @property
    def allowed(self)->bool:
        return all(step.allowed for step in self.steps)

    @property
    def denied(self)->int:
        return sum(not step.allowed for step in self.steps)

    def to_dict(self)->dict[str,object]:
        return {
            "allowed":self.allowed,
            "denied":self.denied,
            "steps":[step.to_dict() for step in self.steps],
        }

class ShellDryRun:
    """Invoke command admission only. Never calls ShellRunner or ShellExecutor."""

    def __init__(self,admission:CommandAdmission)->None:
        self.admission=admission

    def command(
        self,
        command:ShellCommand,
        grant:CapabilityGrant,
        *,
        step_id:str="command",
    )->DryRunReport:
        decision=self.admission.inspect(command,grant)
        return DryRunReport((
            DryRunStep(step_id,decision.allowed,command.command,decision.reason),
        ))

    def plan(
        self,
        plan:ExecutionPlan,
        grant:CapabilityGrant,
    )->DryRunReport:
        steps=[]
        for step in plan.topological_order():
            decision=self.admission.inspect(step.command,grant)
            steps.append(
                DryRunStep(step.step_id,decision.allowed,step.command.command,decision.reason)
            )
        return DryRunReport(tuple(steps))
