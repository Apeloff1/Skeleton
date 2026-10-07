from __future__ import annotations
from dataclasses import dataclass
from .core import Decision, DecisionState, DecisionClass, score_option

@dataclass(frozen=True,slots=True)
class DecisionGuard:
    require_multiple_options:bool=True
    require_assumptions_for_policy:bool=True
    minimum_score:float=.5
    forbid_commit:bool=True

@dataclass(frozen=True,slots=True)
class GuardFinding:
    code:str; message:str; blocking:bool=True

@dataclass(frozen=True,slots=True)
class GuardResult:
    allowed:bool; findings:tuple[GuardFinding,...]

def inspect(decision:Decision,guard:DecisionGuard=DecisionGuard())->GuardResult:
    findings=[]
    if guard.require_multiple_options and len(decision.options)<2: findings.append(GuardFinding("alternatives","multiple options required"))
    if guard.require_assumptions_for_policy and decision.classification is DecisionClass.POLICY and not decision.assumptions: findings.append(GuardFinding("assumptions","policy decisions require explicit assumptions"))
    scores=[score_option(o,decision.criteria) for o in decision.options]
    if max(scores)<guard.minimum_score: findings.append(GuardFinding("threshold","no option meets minimum score"))
    if guard.forbid_commit and decision.state is DecisionState.COMMITTED: findings.append(GuardFinding("authority","decision commit is host-controlled"))
    return GuardResult(not any(x.blocking for x in findings),tuple(findings))
