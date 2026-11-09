"""VS-000 durable bootstrap/restart recovery harness for VOL-096."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
from copy import deepcopy
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class RecoveryError(ValueError):pass
class RecoveryStatus(str,Enum): RECOVERED="recovered"; FAIL_CLOSED="fail_closed"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise RecoveryError(f"{f} must be stable identifier")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class DurableEvent:
 sequence:int;event_id:str;payload:dict;previous_digest:str|None
 def __post_init__(self):
  if not isinstance(self.sequence,int) or isinstance(self.sequence,bool) or self.sequence<1:raise RecoveryError("sequence must be positive integer")
  object.__setattr__(self,"event_id",_id(self.event_id,"event_id"))
  if not isinstance(self.payload,dict):raise RecoveryError("payload must be dict")
  object.__setattr__(self,"payload",deepcopy(self.payload))
  if self.previous_digest is not None and not _SHA.fullmatch(self.previous_digest):raise RecoveryError("previous_digest must be sha256")
  json.dumps(self.payload,sort_keys=True,allow_nan=False)
 @property
 def digest(self):return _dig({"sequence":self.sequence,"event_id":self.event_id,"payload":self.payload,"previous_digest":self.previous_digest})
@dataclass(frozen=True,slots=True)
class RecoveryCheckpoint:
 checkpoint_id:str;through_sequence:int;event_digest:str;projection_digest:str
 def __post_init__(self):
  object.__setattr__(self,"checkpoint_id",_id(self.checkpoint_id,"checkpoint_id"))
  if not isinstance(self.through_sequence,int) or isinstance(self.through_sequence,bool) or self.through_sequence<0:raise RecoveryError("through_sequence invalid")
  for v in (self.event_digest,self.projection_digest):
   if not _SHA.fullmatch(v):raise RecoveryError("checkpoint digests must be sha256")
 @property
 def digest(self):return _dig({"checkpoint_id":self.checkpoint_id,"through_sequence":self.through_sequence,"event_digest":self.event_digest,"projection_digest":self.projection_digest})
@dataclass(frozen=True,slots=True)
class VS000Scenario:
 scenario_id:str;initial_state:dict;events:tuple[DurableEvent,...]
 def __post_init__(self):
  object.__setattr__(self,"scenario_id",_id(self.scenario_id,"scenario_id"))
  if not isinstance(self.initial_state,dict):raise RecoveryError("initial_state must be dict")
  if not isinstance(self.events,tuple) or any(not isinstance(e,DurableEvent) for e in self.events):raise RecoveryError("events must be typed tuple")
  if len(self.events)>100000:raise RecoveryError("event log exceeds recovery bound")
  object.__setattr__(self,"initial_state",deepcopy(self.initial_state));json.dumps(self.initial_state,sort_keys=True,allow_nan=False)
  expected=1;prev=None;event_ids=set()
  for e in self.events:
   if e.event_id in event_ids:raise RecoveryError("duplicate event identity")
   event_ids.add(e.event_id)
   if e.sequence!=expected:raise RecoveryError("event sequence gap")
   if e.previous_digest!=prev:raise RecoveryError("event chain mismatch")
   expected+=1;prev=e.digest
@dataclass(frozen=True,slots=True)
class RecoveryEvidence:
 scenario_id:str;scenario_digest:str;status:RecoveryStatus;checkpoint_digest:str|None;rebuilt_projection_digest:str|None;reason:str
 def __post_init__(self):
  object.__setattr__(self,"scenario_id",_id(self.scenario_id,"scenario_id"))
  if not isinstance(self.status,RecoveryStatus):raise RecoveryError("status must be RecoveryStatus")
  if not _SHA.fullmatch(self.scenario_digest):raise RecoveryError("scenario_digest must be sha256")
  for f in ("checkpoint_digest","rebuilt_projection_digest"):
   v=getattr(self,f)
   if v is not None and (not isinstance(v,str) or not _SHA.fullmatch(v)):raise RecoveryError(f"{f} must be sha256")
  if not isinstance(self.reason,str) or not self.reason.strip():raise RecoveryError("reason must be non-empty")
  if self.checkpoint_digest is None:raise RecoveryError("recovery evidence requires checkpoint digest")
  if self.status is RecoveryStatus.RECOVERED and self.rebuilt_projection_digest is None:raise RecoveryError("recovered evidence requires rebuilt projection digest")
  if self.status is RecoveryStatus.FAIL_CLOSED and self.rebuilt_projection_digest is not None:raise RecoveryError("fail-closed evidence cannot claim rebuilt projection")
 @property
 def digest(self):return _dig({"scenario_id":self.scenario_id,"scenario_digest":self.scenario_digest,"status":self.status.value,"checkpoint_digest":self.checkpoint_digest,"rebuilt_projection_digest":self.rebuilt_projection_digest,"reason":self.reason})
def scenario_digest(scenario:VS000Scenario):
 return _dig({"scenario_id":scenario.scenario_id,"initial_state":scenario.initial_state,"event_digests":[e.digest for e in scenario.events]})
def project(initial,events):
 state=json.loads(json.dumps(initial,sort_keys=True))
 for e in events:
  op=e.payload.get("op");key=e.payload.get("key")
  if op=="set" and isinstance(key,str):state[key]=e.payload.get("value")
  elif op=="delete" and isinstance(key,str):state.pop(key,None)
  else:raise RecoveryError("unsupported event operation")
 return state
def checkpoint(scenario:VS000Scenario,checkpoint_id:str)->RecoveryCheckpoint:
 state=project(scenario.initial_state,scenario.events);last=scenario.events[-1].digest if scenario.events else _dig({"empty":True})
 return RecoveryCheckpoint(checkpoint_id,len(scenario.events),last,_dig(state))
def recover(scenario:VS000Scenario,cp:RecoveryCheckpoint)->RecoveryEvidence:
 try:
  if cp.through_sequence!=len(scenario.events):raise RecoveryError("checkpoint sequence does not cover durable log")
  last=scenario.events[-1].digest if scenario.events else _dig({"empty":True})
  if cp.event_digest!=last:raise RecoveryError("checkpoint event digest mismatch")
  rebuilt=_dig(project(scenario.initial_state,scenario.events))
  if rebuilt!=cp.projection_digest:raise RecoveryError("projection digest mismatch")
  return RecoveryEvidence(scenario.scenario_id,scenario_digest(scenario),RecoveryStatus.RECOVERED,cp.digest,rebuilt,"deterministic rebuild matched checkpoint")
 except RecoveryError as exc:
  return RecoveryEvidence(scenario.scenario_id,scenario_digest(scenario),RecoveryStatus.FAIL_CLOSED,cp.digest,None,str(exc))
