"""Durable training control plane for VOL-143."""
from __future__ import annotations
from dataclasses import dataclass,replace
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class TrainingError(ValueError):pass
class RunState(str,Enum): ADMITTED="admitted"; RUNNING="running"; CHECKPOINTED="checkpointed"; SUCCEEDED="succeeded"; FAILED="failed"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise TrainingError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise TrainingError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class TrainingConfig:
 config_id:str;dataset_version_id:str;base_model_id:str;hyperparameters_digest:str
 def __post_init__(self):
  for f in ("config_id","dataset_version_id","base_model_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.hyperparameters_digest,"hyperparameters_digest")
 @property
 def digest(self):return _dig([self.config_id,self.dataset_version_id,self.base_model_id,self.hyperparameters_digest])
@dataclass(frozen=True,slots=True)
class TrainingAdmission:
 admission_id:str;config_digest:str;cpu_units:int;accelerator_units:int;memory_bytes:int;budget_units:int
 def __post_init__(self):
  object.__setattr__(self,"admission_id",_id(self.admission_id,"admission_id"));_sha(self.config_digest,"config_digest")
  if min(self.cpu_units,self.memory_bytes,self.budget_units)<1 or self.accelerator_units<0:raise TrainingError("positive resource admission required")
@dataclass(frozen=True,slots=True)
class TrainingRun:
 run_id:str;config_digest:str;admission_id:str;state:RunState;checkpoint_digest:str|None=None;evidence_digest:str|None=None
 def __post_init__(self):
  object.__setattr__(self,"run_id",_id(self.run_id,"run_id"));_sha(self.config_digest,"config_digest");object.__setattr__(self,"admission_id",_id(self.admission_id,"admission_id"))
  if self.checkpoint_digest:_sha(self.checkpoint_digest,"checkpoint_digest")
  if self.evidence_digest:_sha(self.evidence_digest,"evidence_digest")
class TrainingControlPlane:
 def __init__(self,registered_datasets,registered_models):
  self.datasets=set(registered_datasets);self.models=set(registered_models);self.runs={}
 def admit(self,run_id,config,admission):
  if config.dataset_version_id not in self.datasets or config.base_model_id not in self.models:raise TrainingError("unregistered training input")
  if admission.config_digest!=config.digest:raise TrainingError("admission/config mismatch")
  if run_id in self.runs:raise TrainingError("duplicate run")
  run=TrainingRun(run_id,config.digest,admission.admission_id,RunState.ADMITTED);self.runs[run_id]=run;return run
 def transition(self,run_id,state,checkpoint_digest=None,evidence_digest=None):
  run=self.runs[run_id];allowed={RunState.ADMITTED:{RunState.RUNNING,RunState.FAILED},RunState.RUNNING:{RunState.CHECKPOINTED,RunState.SUCCEEDED,RunState.FAILED},RunState.CHECKPOINTED:{RunState.RUNNING,RunState.SUCCEEDED,RunState.FAILED},RunState.SUCCEEDED:set(),RunState.FAILED:set()}
  if state not in allowed[run.state]:raise TrainingError("illegal training transition")
  if state is RunState.CHECKPOINTED and not checkpoint_digest:raise TrainingError("checkpoint state requires digest")
  if state in (RunState.SUCCEEDED,RunState.FAILED) and not evidence_digest:raise TrainingError("terminal state requires evidence")
  nxt=replace(run,state=state,checkpoint_digest=checkpoint_digest or run.checkpoint_digest,evidence_digest=evidence_digest or run.evidence_digest);self.runs[run_id]=nxt;return nxt
