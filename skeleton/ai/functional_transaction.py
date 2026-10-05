"""Provider-neutral authoritative AI transaction contract for VOL-097."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
from copy import deepcopy
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class FunctionalAIError(ValueError):pass
class ExecutionState(str,Enum): PREPARED="prepared"; INFERRED="inferred"; AUTHORIZED="authorized"; COMMITTED="committed"; FAILED="failed"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise FunctionalAIError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise FunctionalAIError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class VS001Request:
 request_id:str;conversation_id:str;objective:str;durable_state_digest:str;context_digest:str
 def __post_init__(self):
  for f in ("request_id","conversation_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  if not isinstance(self.objective,str) or not self.objective.strip():raise FunctionalAIError("objective required")
  object.__setattr__(self,"objective",self.objective.strip())
  _sha(self.durable_state_digest,"durable_state_digest");_sha(self.context_digest,"context_digest")
 @property
 def digest(self):return _dig({"request_id":self.request_id,"conversation_id":self.conversation_id,"objective":self.objective,"durable_state_digest":self.durable_state_digest,"context_digest":self.context_digest})
@dataclass(frozen=True,slots=True)
class InferenceOutcome:
 provider_id:str;request_digest:str;response_digest:str;tool_intent_digest:str|None
 def __post_init__(self):
  object.__setattr__(self,"provider_id",_id(self.provider_id,"provider_id"));_sha(self.request_digest,"request_digest");_sha(self.response_digest,"response_digest")
  if self.tool_intent_digest is not None:_sha(self.tool_intent_digest,"tool_intent_digest")
@dataclass(frozen=True,slots=True)
class ToolAuthorization:
 authorization_id:str;request_digest:str;tool_intent_digest:str;authority_id:str;allowed:bool
 def __post_init__(self):
  for f in ("authorization_id","authority_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.request_digest,"request_digest");_sha(self.tool_intent_digest,"tool_intent_digest")
  if not isinstance(self.allowed,bool):raise FunctionalAIError("allowed must be bool")
@dataclass(frozen=True,slots=True)
class VS001Execution:
 execution_id:str;request:VS001Request;inference:InferenceOutcome;authorization:ToolAuthorization|None;tool_result_digest:str|None;verified:bool=True
 def __post_init__(self):
  object.__setattr__(self,"execution_id",_id(self.execution_id,"execution_id"))
  if not isinstance(self.request,VS001Request) or not isinstance(self.inference,InferenceOutcome):raise FunctionalAIError("execution inputs must be typed")
  if not isinstance(self.verified,bool):raise FunctionalAIError("verified must be bool")
  if self.inference.request_digest!=self.request.digest:raise FunctionalAIError("inference/request mismatch")
  if self.inference.tool_intent_digest is None:
   if self.authorization is not None or self.tool_result_digest is not None:raise FunctionalAIError("tool material without tool intent")
  else:
   if self.authorization is None:raise FunctionalAIError("tool intent requires explicit authorization")
   if self.authorization.request_digest!=self.request.digest or self.authorization.tool_intent_digest!=self.inference.tool_intent_digest:raise FunctionalAIError("authorization identity mismatch")
   if not self.authorization.allowed and self.tool_result_digest is not None:raise FunctionalAIError("denied tool cannot produce result")
   if self.authorization.allowed and self.tool_result_digest is None:raise FunctionalAIError("authorized tool requires verified result")
   if self.tool_result_digest is not None:_sha(self.tool_result_digest,"tool_result_digest")
 @property
 def digest(self):return _dig({"execution_id":self.execution_id,"request":self.request.digest,"provider":self.inference.provider_id,"response":self.inference.response_digest,"tool_intent":self.inference.tool_intent_digest,"authorization":None if self.authorization is None else {"id":self.authorization.authorization_id,"authority":self.authorization.authority_id,"allowed":self.authorization.allowed},"tool_result":self.tool_result_digest,"verified":self.verified})
@dataclass(frozen=True,slots=True)
class VS001Evidence:
 execution_digest:str;terminal_state_digest:str;stream_digest:str;frame_count:int
 def __post_init__(self):
  _sha(self.execution_digest,"execution_digest");_sha(self.terminal_state_digest,"terminal_state_digest");_sha(self.stream_digest,"stream_digest")
  if not isinstance(self.frame_count,int) or isinstance(self.frame_count,bool) or self.frame_count<1:raise FunctionalAIError("frame_count must be positive integer")
class FunctionalAIJournal:
 def __init__(self):self._terminal={};self._frames={}
 def commit(self,execution:VS001Execution,terminal_state:dict,stream_frames:tuple[dict,...])->VS001Evidence:
  if not isinstance(execution,VS001Execution):raise FunctionalAIError("execution must be VS001Execution")
  if not execution.verified:raise FunctionalAIError("unverified execution cannot commit terminal state")
  if not isinstance(terminal_state,dict):raise FunctionalAIError("terminal_state must be dict")
  if not isinstance(stream_frames,tuple) or not stream_frames or any(not isinstance(x,dict) for x in stream_frames):raise FunctionalAIError("stream_frames must be non-empty typed tuple")
  if len(stream_frames)>100000:raise FunctionalAIError("stream frame count exceeds policy bound")
  terminal_state=deepcopy(terminal_state);stream_frames=deepcopy(stream_frames)
  json.dumps(terminal_state,sort_keys=True,allow_nan=False);json.dumps(stream_frames,sort_keys=True,allow_nan=False)
  terminal=_dig(terminal_state);stream=_dig(stream_frames);e=VS001Evidence(execution.digest,terminal,stream,len(stream_frames))
  prior=self._terminal.get(execution.request.request_id)
  if prior is not None and prior!=e:raise FunctionalAIError("terminal outcome is immutable")
  self._terminal[execution.request.request_id]=e;self._frames[execution.request.request_id]=stream_frames;return e
 def replay(self,request_id:str)->VS001Evidence:
  _id(request_id,"request_id")
  if request_id not in self._terminal:raise FunctionalAIError("no committed terminal outcome")
  return self._terminal[request_id]

 def replay_frames(self,request_id:str)->tuple[dict,...]:
  evidence=self.replay(request_id);frames=deepcopy(self._frames[request_id])
  if len(frames)!=evidence.frame_count or _dig(frames)!=evidence.stream_digest:raise FunctionalAIError("authoritative stream diverged from committed evidence")
  return frames
