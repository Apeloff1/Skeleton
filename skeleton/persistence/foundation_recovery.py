"""VS-000 durable bootstrap/restart recovery harness for VOL-096."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
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
  if not isinstance(self.sequence,int) or self.sequence<1:raise RecoveryError("sequence must be positive")
  object.__setattr__(self,"event_id",_id(self.event_id,"event_id"))
  if self.previous_digest is not None and not _SHA.fullmatch(self.previous_digest):raise RecoveryError("previous_digest must be sha256")
  json.dumps(self.payload,sort_keys=True,allow_nan=False)
 @property
 def digest(self):return _dig({"sequence":self.sequence,"event_id":self.event_id,"payload":self.payload,"previous_digest":self.previous_digest})
@dataclass(frozen=True,slots=True)
class RecoveryCheckpoint:
 checkpoint_id:str;through_sequence:int;event_digest:str;projection_digest:str
 def __post_init__(self):
  object.__setattr__(self,"checkpoint_id",_id(self.checkpoint_id,"checkpoint_id"))
  if self.through_sequence<0:raise RecoveryError("through_sequence invalid")
  for v in (self.event_digest,self.projection_digest):
   if not _SHA.fullmatch(v):raise RecoveryError("checkpoint digests must be sha256")
 @property
 def digest(self):return _dig({"checkpoint_id":self.checkpoint_id,"through_sequence":self.through_sequence,"event_digest":self.event_digest,"projection_digest":self.projection_digest})
@dataclass(frozen=True,slots=True)
class VS000Scenario:
 scenario_id:str;initial_state:dict;events:tuple[DurableEvent,...]
 def __post_init__(self):
  object.__setattr__(self,"scenario_id",_id(self.scenario_id,"scenario_id"));json.dumps(self.initial_state,sort_keys=True,allow_nan=False)
  expected=1;prev=None
  for e in self.events:
   if e.sequence!=expected:raise RecoveryError("event sequence gap")
   if e.previous_digest!=prev:raise RecoveryError("event chain mismatch")
   expected+=1;prev=e.digest
@dataclass(frozen=True,slots=True)
class RecoveryEvidence:
 scenario_id:str;status:RecoveryStatus;checkpoint_digest:str|None;rebuilt_projection_digest:str|None;reason:str
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
  return RecoveryEvidence(scenario.scenario_id,RecoveryStatus.RECOVERED,cp.digest,rebuilt,"deterministic rebuild matched checkpoint")
 except RecoveryError as exc:
  return RecoveryEvidence(scenario.scenario_id,RecoveryStatus.FAIL_CLOSED,cp.digest,None,str(exc))
