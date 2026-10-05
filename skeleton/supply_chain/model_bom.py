"""Privacy-preserving immutable model bill of materials for VOL-179."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class MBOMError(ValueError):pass
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise MBOMError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class ModelComponent:
 component_id:str;kind:str;artifact_digest:str
 def __post_init__(self):
  if not _ID.fullmatch(self.component_id) or self.kind not in {"base_model","adapter","tokenizer","runtime"}:raise MBOMError("invalid model component")
  _sha(self.artifact_digest,"artifact_digest")
@dataclass(frozen=True,slots=True)
class ModelLineage:
 training_run_id:str;training_evidence_digest:str;dataset_ref_digest:str;post_training_run_id:str|None=None;post_training_evidence_digest:str|None=None
 def __post_init__(self):
  if not _ID.fullmatch(self.training_run_id):raise MBOMError("invalid training run")
  _sha(self.training_evidence_digest,"training_evidence_digest");_sha(self.dataset_ref_digest,"dataset_ref_digest")
  if self.post_training_run_id and not _ID.fullmatch(self.post_training_run_id):raise MBOMError("invalid post training run")
  if bool(self.post_training_run_id)!=bool(self.post_training_evidence_digest):raise MBOMError("post training lineage incomplete")
  if self.post_training_evidence_digest:_sha(self.post_training_evidence_digest,"post_training_evidence_digest")
@dataclass(frozen=True,slots=True)
class MBOM:
 model_id:str;model_artifact_digest:str;components:tuple[ModelComponent,...];lineage:ModelLineage
 def __post_init__(self):
  if not _ID.fullmatch(self.model_id) or not self.components:raise MBOMError("invalid MBOM")
  _sha(self.model_artifact_digest,"model_artifact_digest")
  ids=[x.component_id for x in self.components]
  if len(ids)!=len(set(ids)):raise MBOMError("duplicate component")
 @property
 def digest(self):
  body={"model_id":self.model_id,"model":self.model_artifact_digest,"components":sorted((x.component_id,x.kind,x.artifact_digest) for x in self.components),"lineage":(self.lineage.training_run_id,self.lineage.training_evidence_digest,self.lineage.dataset_ref_digest,self.lineage.post_training_run_id,self.lineage.post_training_evidence_digest)}
  return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
