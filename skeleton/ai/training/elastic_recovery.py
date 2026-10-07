"""Elastic training epoch and stale-worker fencing for VOL-146."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class ElasticError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise ElasticError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise ElasticError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class TrainingEpoch:
 run_id:str;epoch:int;checkpoint_digest:str;data_position_digest:str
 def __post_init__(self):
  object.__setattr__(self,"run_id",_id(self.run_id,"run_id"))
  if self.epoch<1:raise ElasticError("epoch must be positive")
  _sha(self.checkpoint_digest,"checkpoint_digest");_sha(self.data_position_digest,"data_position_digest")
@dataclass(frozen=True,slots=True)
class WorkerFence:
 worker_id:str;run_id:str;epoch:int;token:int
 def __post_init__(self):
  object.__setattr__(self,"worker_id",_id(self.worker_id,"worker_id"));object.__setattr__(self,"run_id",_id(self.run_id,"run_id"))
  if self.epoch<1 or self.token<1:raise ElasticError("fence epoch/token must be positive")
@dataclass(frozen=True,slots=True)
class ElasticResume:
 prior_epoch:int;new_epoch:int;checkpoint_digest:str;data_position_digest:str
 def __post_init__(self):
  if self.new_epoch!=self.prior_epoch+1:raise ElasticError("resume must advance exactly one epoch")
  _sha(self.checkpoint_digest,"checkpoint_digest");_sha(self.data_position_digest,"data_position_digest")
class ElasticCoordinator:
 def __init__(self,epoch):self.epoch=epoch;self._next_token=0;self._fences={}
 def fence(self,worker_id):
  self._next_token+=1;f=WorkerFence(worker_id,self.epoch.run_id,self.epoch.epoch,self._next_token);self._fences[worker_id]=f;return f
 def authorize_write(self,fence):
  current=self._fences.get(fence.worker_id)
  if fence.run_id!=self.epoch.run_id or fence.epoch!=self.epoch.epoch or current!=fence:raise ElasticError("stale worker fence")
  return True
 def recover(self,resume):
  if resume.prior_epoch!=self.epoch.epoch or resume.checkpoint_digest!=self.epoch.checkpoint_digest or resume.data_position_digest!=self.epoch.data_position_digest:raise ElasticError("resume state mismatch")
  self.epoch=TrainingEpoch(self.epoch.run_id,resume.new_epoch,resume.checkpoint_digest,resume.data_position_digest);self._fences.clear();return self.epoch
