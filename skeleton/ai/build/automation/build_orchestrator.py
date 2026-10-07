"""Pure decision engine for autonomous build continuation."""
from __future__ import annotations
from dataclasses import dataclass
from .ci_failure_attribution import attribute
@dataclass(frozen=True)
class OrchestrationDecision:
 action:str;reason:str;repair_gates:tuple[str,...]=()
def decide(*,campaign_status:str,build_status:str,ci_complete:bool,failed_gates:tuple[str,...],fresh_supervisor:bool,operator_hold:bool)->OrchestrationDecision:
 if operator_hold:return OrchestrationDecision("stop","operator hold")
 if campaign_status in {"quarantined","exhausted"} or build_status in {"quarantined","exhausted"}:return OrchestrationDecision("stop","controller terminal failure")
 if failed_gates:
  attrs=tuple(attribute(g) for g in failed_gates)
  if any(not a.retryable for a in attrs):return OrchestrationDecision("quarantine","non-retryable CI failure",failed_gates)
  return OrchestrationDecision("repair","retryable exact-head CI failure",failed_gates)
 if campaign_status=="complete" and build_status=="complete":
  return OrchestrationDecision("certify" if ci_complete else "wait_ci","controllers complete")
 if not fresh_supervisor:return OrchestrationDecision("refresh_supervisor","canonical authority must advance")
 return OrchestrationDecision("continue","bounded work remains")
