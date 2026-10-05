"""Reliability controls for VOL-288..292."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class PressureLevel(str,Enum): NORMAL="normal"; HIGH="high"; SATURATED="saturated"
@dataclass(frozen=True,slots=True)
class BufferLimit:
 capacity:int; high_watermark:int
 def __post_init__(self):
  if self.capacity<=0 or not 0<self.high_watermark<=self.capacity: raise ValueError("invalid buffer limits")
@dataclass(frozen=True,slots=True)
class BackpressureSignal: depth:int; limit:BufferLimit; cancelled:bool=False
@dataclass(frozen=True,slots=True)
class PressureDecision: level:PressureLevel; accept_new:bool; throttle:bool; cancelled:bool
def pressure(s:BackpressureSignal)->PressureDecision:
 if s.depth<0:raise ValueError("queue depth must be nonnegative")
 if s.cancelled:return PressureDecision(PressureLevel.SATURATED,False,False,True)
 if s.depth>=s.limit.capacity:return PressureDecision(PressureLevel.SATURATED,False,True,False)
 if s.depth>=s.limit.high_watermark:return PressureDecision(PressureLevel.HIGH,True,True,False)
 return PressureDecision(PressureLevel.NORMAL,True,False,False)

class WorkClass(str,Enum): OPTIONAL="optional"; NORMAL="normal"; RECOVERY="recovery"; SECURITY="security"; AUDIT="audit"; AUTHORITY="authority"
@dataclass(frozen=True,slots=True)
class LoadShedPolicy: shed_classes:tuple[WorkClass,...]
@dataclass(frozen=True,slots=True)
class ShedDecision: work_class:WorkClass; shed:bool; degraded_response:str|None
def shed(policy:LoadShedPolicy,work_class:WorkClass)->ShedDecision:
 if len(set(policy.shed_classes))!=len(policy.shed_classes):raise ValueError("duplicate shed class")
 protected={WorkClass.SECURITY,WorkClass.AUDIT,WorkClass.AUTHORITY}
 if work_class in protected:return ShedDecision(work_class,False,None)
 yes=work_class in policy.shed_classes
 return ShedDecision(work_class,yes,"overloaded" if yes else None)

@dataclass(frozen=True,slots=True)
class QueueBudget: max_depth:int; max_age:int
@dataclass(frozen=True,slots=True)
class CongestionState: depth:int; oldest_age:int; service_rate:float
class QueueKind(str,Enum): NEW="new"; RETRY="retry"; RECOVERY="recovery"
@dataclass(frozen=True,slots=True)
class QueueDecision: kind:QueueKind; admit:bool; drain_first:bool; reason:str
def queue_decision(b:QueueBudget,s:CongestionState,k:QueueKind)->QueueDecision:
 if b.max_depth<1 or b.max_age<0 or s.depth<0 or s.oldest_age<0 or s.service_rate<0:raise ValueError("invalid queue budget/state")
 congested=s.depth>=b.max_depth or s.oldest_age>=b.max_age
 if not congested:return QueueDecision(k,True,False,"within budget")
 if k is QueueKind.RECOVERY:return QueueDecision(k,True,True,"recovery drain")
 return QueueDecision(k,False,True,"queue budget exceeded")

class FailureClass(str,Enum): TRANSIENT="transient"; PERMANENT="permanent"; POLICY="policy"; UNKNOWN="unknown"
@dataclass(frozen=True,slots=True)
class RetryBudget: budget_id:str; max_attempts:int; consumed:int=0
 def __post_init__(self):
  if not self.budget_id or self.max_attempts<0 or not 0<=self.consumed<=self.max_attempts: raise ValueError("invalid retry budget")
@dataclass(frozen=True,slots=True)
class RetryAttempt: budget_id:str; failure:FailureClass; idempotent:bool
@dataclass(frozen=True,slots=True)
class RetryDecision: allowed:bool; next_budget:RetryBudget; reason:str
def retry(b:RetryBudget,a:RetryAttempt)->RetryDecision:
 if a.budget_id!=b.budget_id:return RetryDecision(False,b,"budget identity mismatch")
 if a.failure is not FailureClass.TRANSIENT:return RetryDecision(False,b,"failure not transient")
 if not a.idempotent:return RetryDecision(False,b,"operation not idempotent")
 if b.consumed>=b.max_attempts:return RetryDecision(False,b,"budget exhausted")
 return RetryDecision(True,RetryBudget(b.budget_id,b.max_attempts,b.consumed+1),"retry admitted")

class BreakerState(str,Enum): CLOSED="closed"; OPEN="open"; HALF_OPEN="half_open"
@dataclass(frozen=True,slots=True)
class CircuitBreaker: dependency_id:str; failure_domain:str; state:BreakerState; threshold:int; failures:int
@dataclass(frozen=True,slots=True)
class ProbeResult: dependency_id:str; success:bool
@dataclass(frozen=True,slots=True)
class BreakerDecision: state:BreakerState; allow_primary:bool; fallback_allowed:bool
def breaker(b:CircuitBreaker,probe:ProbeResult|None=None,*,fallback_policy_compatible:bool=False)->BreakerDecision:
 if probe is not None and probe.dependency_id!=b.dependency_id: raise ValueError("probe belongs to another dependency")
 if b.state is BreakerState.OPEN:
  if probe is None:return BreakerDecision(BreakerState.OPEN,False,fallback_policy_compatible)
  return BreakerDecision(BreakerState.CLOSED if probe.success else BreakerState.OPEN,probe.success,fallback_policy_compatible)
 if b.failures>=b.threshold:return BreakerDecision(BreakerState.OPEN,False,fallback_policy_compatible)
 return BreakerDecision(b.state,True,False)
