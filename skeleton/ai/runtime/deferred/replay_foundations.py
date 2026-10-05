"""Isolation, replay and deterministic foundation contracts VOL-293..299."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

@dataclass(frozen=True,slots=True)
class BulkheadLimit: concurrency:int; capacity:int
@dataclass(frozen=True,slots=True)
class Bulkhead: bulkhead_id:str; domain:str; limit:BulkheadLimit; active:int
@dataclass(frozen=True,slots=True)
class OverflowDecision: admitted:bool; target_bulkhead:str|None; reason:str
def overflow(source:Bulkhead,target:Bulkhead|None,*,authority_compatible:bool)->OverflowDecision:
 if source.active<source.limit.concurrency:return OverflowDecision(True,source.bulkhead_id,"source capacity")
 if target and authority_compatible and target.active<target.limit.concurrency:return OverflowDecision(True,target.bulkhead_id,"explicit overflow")
 return OverflowDecision(False,None,"isolated capacity exhausted")

@dataclass(frozen=True,slots=True)
class DeadLetter:
 operation_id:str; payload_digest:str; attempts:int; failure_cause:str; idempotency_key:str|None
@dataclass(frozen=True,slots=True)
class ReplayAuthorization:
 operation_id:str; current_authorization:bool; compatibility_verified:bool; idempotency_verified:bool
class DeadLetterDisposition(str,Enum): HOLD="hold"; REPLAY="replay"; DISCARD="discard"
def dead_letter_disposition(d:DeadLetter,a:ReplayAuthorization)->DeadLetterDisposition:
 if d.operation_id!=a.operation_id:return DeadLetterDisposition.HOLD
 if a.current_authorization and a.compatibility_verified and a.idempotency_verified:return DeadLetterDisposition.REPLAY
 return DeadLetterDisposition.HOLD

class ReplayMode(str,Enum): RECONSTRUCT="reconstruct"; SIMULATE="simulate"; REAL_EFFECT="real_effect"
@dataclass(frozen=True,slots=True)
class ReplayRequest: operation_id:str; mode:ReplayMode; reconciled:bool=False; idempotent:bool=False
@dataclass(frozen=True,slots=True)
class ReplayResult: operation_id:str; allowed:bool; external_effects:bool; reason:str
def replay(r:ReplayRequest)->ReplayResult:
 if r.mode is not ReplayMode.REAL_EFFECT:return ReplayResult(r.operation_id,True,False,r.mode.value)
 ok=r.reconciled and r.idempotent
 return ReplayResult(r.operation_id,ok,ok,"effect replay admitted" if ok else "effect replay requires reconciliation and idempotency")

class DeterminismClass(str,Enum): EXACT="exact"; TOLERANT="tolerant"; NONDETERMINISTIC="nondeterministic"
@dataclass(frozen=True,slots=True)
class VariancePolicy: absolute_tolerance:float; relative_tolerance:float
@dataclass(frozen=True,slots=True)
class DeterminismEnvelope:
 classification:DeterminismClass; seed:int|None; variance:VariancePolicy; nondeterminism_sources:tuple[str,...]
 def equivalent(self,a:float,b:float)->bool:
  if self.classification is DeterminismClass.EXACT:return a==b
  if self.classification is DeterminismClass.NONDETERMINISTIC:return False
  return abs(a-b)<=max(self.variance.absolute_tolerance,self.variance.relative_tolerance*max(abs(a),abs(b)))

@dataclass(frozen=True,slots=True)
class Instant: unix_ns:int; timezone:str|None=None
@dataclass(frozen=True,slots=True)
class Duration: monotonic_ns:int
 def __post_init__(self):
  if self.monotonic_ns<0: raise ValueError("duration must be monotonic/non-negative")
@dataclass(frozen=True,slots=True)
class Deadline:
 start_monotonic_ns:int; duration:Duration
 def expired(self,now_monotonic_ns:int)->bool:return now_monotonic_ns-self.start_monotonic_ns>=self.duration.monotonic_ns

class IdentifierKind(str,Enum): OPERATION="operation"; PRINCIPAL="principal"; RESOURCE="resource"
@dataclass(frozen=True,slots=True)
class Identifier:
 kind:IdentifierKind; value:str
class IdentifierCodec:
 @staticmethod
 def parse(text:str)->Identifier:
  if text!=text.strip() or text.lower()!=text or text.count(":")!=1: raise ValueError("ambiguous identifier")
  k,v=text.split(":")
  if not v or any(ch.isspace() for ch in v): raise ValueError("ambiguous identifier")
  return Identifier(IdentifierKind(k),v)
 @staticmethod
 def render(i:Identifier)->str:return f"{i.kind.value}:{i.value}"

@dataclass(frozen=True,slots=True)
class SequenceNumber: domain:str; value:int
@dataclass(frozen=True,slots=True)
class LogicalClock:
 node_id:str; counter:int
 def tick(self)->"LogicalClock": return LogicalClock(self.node_id,self.counter+1)
class CausalRelation(str,Enum): BEFORE="before"; AFTER="after"; CONCURRENT="concurrent"; UNKNOWN="unknown"
def compare_sequence(a:SequenceNumber,b:SequenceNumber)->CausalRelation:
 if a.domain!=b.domain:return CausalRelation.UNKNOWN
 if a.value<b.value:return CausalRelation.BEFORE
 if a.value>b.value:return CausalRelation.AFTER
 return CausalRelation.CONCURRENT
