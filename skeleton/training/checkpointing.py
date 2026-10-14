"""Semantically complete training checkpoints for VOL-145."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class CheckpointError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise CheckpointError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise CheckpointError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class CheckpointManifest:
 model_digest:str;optimizer_digest:str;scheduler_digest:str;rng_digest:str;data_position_digest:str;config_digest:str;schema_version:int
 def __post_init__(self):
  for f in ("model_digest","optimizer_digest","scheduler_digest","rng_digest","data_position_digest","config_digest"):_sha(getattr(self,f),f)
  if self.schema_version<1:raise CheckpointError("schema version must be positive")
 @property
 def digest(self):return _dig([self.model_digest,self.optimizer_digest,self.scheduler_digest,self.rng_digest,self.data_position_digest,self.config_digest,self.schema_version])
@dataclass(frozen=True,slots=True)
class TrainingCheckpoint:
 checkpoint_id:str;run_id:str;manifest:CheckpointManifest;artifact_digest:str
 def __post_init__(self):
  object.__setattr__(self,"checkpoint_id",_id(self.checkpoint_id,"checkpoint_id"));object.__setattr__(self,"run_id",_id(self.run_id,"run_id"));_sha(self.artifact_digest,"artifact_digest")
@dataclass(frozen=True,slots=True)
class ResumeState:
 checkpoint_id:str;manifest_digest:str;expected_config_digest:str;restored_artifact_digest:str
 def __post_init__(self):
  object.__setattr__(self,"checkpoint_id",_id(self.checkpoint_id,"checkpoint_id"))
  for f in ("manifest_digest","expected_config_digest","restored_artifact_digest"):_sha(getattr(self,f),f)
def validate_resume(checkpoint,resume,supported_schema):
 if resume.checkpoint_id!=checkpoint.checkpoint_id:raise CheckpointError("checkpoint identity mismatch")
 if resume.manifest_digest!=checkpoint.manifest.digest:raise CheckpointError("manifest digest mismatch")
 if resume.expected_config_digest!=checkpoint.manifest.config_digest:raise CheckpointError("configuration incompatible")
 if resume.restored_artifact_digest!=checkpoint.artifact_digest:raise CheckpointError("artifact integrity mismatch")
 if checkpoint.manifest.schema_version not in supported_schema:raise CheckpointError("checkpoint schema incompatible")
 return True
