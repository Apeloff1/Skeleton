"""Isolated post-training experiment lineage for VOL-149."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class PostTrainingError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise PostTrainingError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise PostTrainingError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class PreferenceDataset:
 dataset_id:str;version_digest:str;rights_digest:str
 def __post_init__(self):
  object.__setattr__(self,"dataset_id",_id(self.dataset_id,"dataset_id"));_sha(self.version_digest,"version_digest");_sha(self.rights_digest,"rights_digest")
@dataclass(frozen=True,slots=True)
class PostTrainingRun:
 run_id:str;base_model_digest:str;dataset:PreferenceDataset;objective_digest:str;algorithm_id:str;config_digest:str
 def __post_init__(self):
  object.__setattr__(self,"run_id",_id(self.run_id,"run_id"));object.__setattr__(self,"algorithm_id",_id(self.algorithm_id,"algorithm_id"))
  for f in ("base_model_digest","objective_digest","config_digest"):_sha(getattr(self,f),f)
 @property
 def lineage_digest(self):return _dig([self.run_id,self.base_model_digest,self.dataset.dataset_id,self.dataset.version_digest,self.dataset.rights_digest,self.objective_digest,self.algorithm_id,self.config_digest])
@dataclass(frozen=True,slots=True)
class PostTrainingCandidate:
 candidate_id:str;run_lineage_digest:str;model_digest:str;evaluation_evidence_digest:str|None=None
 def __post_init__(self):
  object.__setattr__(self,"candidate_id",_id(self.candidate_id,"candidate_id"));_sha(self.run_lineage_digest,"run_lineage_digest");_sha(self.model_digest,"model_digest")
  if self.evaluation_evidence_digest:_sha(self.evaluation_evidence_digest,"evaluation_evidence_digest")
 @property
 def experimentally_qualified(self):return self.evaluation_evidence_digest is not None
 def production_authorized(self):return False
