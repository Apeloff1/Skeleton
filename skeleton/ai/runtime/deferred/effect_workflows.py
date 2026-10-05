"""Durable side effects, compensation and saga workflows VOL-378..380."""
from dataclasses import dataclass
from enum import Enum
class EffectState(str,Enum): PLANNED="planned"; ATTEMPTED="attempted"; CONFIRMED="confirmed"; UNKNOWN="unknown"
@dataclass(frozen=True,slots=True)
class SideEffect: effect_id:str; operation_id:str; idempotency_key:str; effect_class:str
@dataclass(frozen=True,slots=True)
class EffectAttempt: effect:SideEffect; precommitted:bool
@dataclass(frozen=True,slots=True)
class EffectReceipt: effect_id:str; state:EffectState; reconciliation_required:bool
def effect_receipt(a,outcome):
 if not all((a.effect.effect_id,a.effect.operation_id,a.effect.idempotency_key,a.effect.effect_class)):raise ValueError("complete side-effect identity required")
 if not a.precommitted:return EffectReceipt(a.effect.effect_id,EffectState.UNKNOWN,True)
 if outcome is True:return EffectReceipt(a.effect.effect_id,EffectState.CONFIRMED,False)
 if outcome is False:return EffectReceipt(a.effect.effect_id,EffectState.ATTEMPTED,False)
 return EffectReceipt(a.effect.effect_id,EffectState.UNKNOWN,True)
@dataclass(frozen=True,slots=True)
class CompensationStep: step_id:str; compensates_effect_id:str; idempotency_key:str
@dataclass(frozen=True,slots=True)
class Compensation: compensation_id:str; steps:tuple[CompensationStep,...]
@dataclass(frozen=True,slots=True)
class CompensationResult: compensation_id:str; succeeded:bool; reconciliation_required:bool
def compensation_result(c,step_results):
 if not c.compensation_id or not c.steps or any(not all((s.step_id,s.compensates_effect_id,s.idempotency_key)) for s in c.steps):raise ValueError("complete compensation identity required")
 if len({s.step_id for s in c.steps})!=len(c.steps):raise ValueError("duplicate compensation step")
 ok=len(step_results)==len(c.steps) and all(step_results)
 return CompensationResult(c.compensation_id,ok,not ok)
@dataclass(frozen=True,slots=True)
class SagaDefinition: saga_id:str; steps:tuple[str,...]; idempotency_keys:tuple[str,...]; timeouts:tuple[int,...]; compensations:tuple[str|None,...]
@dataclass(frozen=True,slots=True)
class SagaInstance: saga_id:str; instance_id:str; completed:int; durable_revision:int
@dataclass(frozen=True,slots=True)
class SagaTransition: previous_revision:int; revision:int; completed:int
def advance_saga(d,i):
 if d.saga_id!=i.saga_id or not(len(d.steps)==len(d.idempotency_keys)==len(d.timeouts)==len(d.compensations)):raise ValueError("invalid saga")
 if i.completed>=len(d.steps):return i,SagaTransition(i.durable_revision,i.durable_revision,i.completed)
 n=SagaInstance(i.saga_id,i.instance_id,i.completed+1,i.durable_revision+1)
 return n,SagaTransition(i.durable_revision,n.durable_revision,n.completed)
