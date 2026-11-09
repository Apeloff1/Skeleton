"""Evidence-bound checkpoint evaluation and promotion gates for VOL-148."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class GateError(ValueError):pass
class Result(str,Enum): PASS="pass"; REGRESSION="regression"; UNCERTAIN="uncertain"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise GateError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise GateError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class TrainingEvalGate:
 gate_id:str;suite_id:str;suite_digest:str;required_metric_ids:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"gate_id",_id(self.gate_id,"gate_id"));object.__setattr__(self,"suite_id",_id(self.suite_id,"suite_id"));_sha(self.suite_digest,"suite_digest")
  if not self.required_metric_ids:raise GateError("evaluation metrics required")
@dataclass(frozen=True,slots=True)
class CheckpointEvaluation:
 gate_id:str;checkpoint_digest:str;champion_digest:str;results:tuple[tuple[str,Result],...];evidence_digest:str
 def __post_init__(self):
  object.__setattr__(self,"gate_id",_id(self.gate_id,"gate_id"))
  for f in ("checkpoint_digest","champion_digest","evidence_digest"):_sha(getattr(self,f),f)
@dataclass(frozen=True,slots=True)
class ModelPromotion:
 gate_id:str;checkpoint_digest:str;evidence_digest:str;dispositions:tuple[tuple[str,str],...]
def promote(gate,evaluation,dispositions=()):
 if evaluation.gate_id!=gate.gate_id:raise GateError("gate/evaluation mismatch")
 observed={k:v for k,v in evaluation.results}
 if set(observed)!=set(gate.required_metric_ids):raise GateError("evaluation metric set mismatch")
 disp=dict(dispositions)
 unresolved=[k for k,v in observed.items() if v is not Result.PASS and not disp.get(k,"").strip()]
 if unresolved:raise GateError("regression or uncertainty requires explicit disposition")
 return ModelPromotion(gate.gate_id,evaluation.checkpoint_digest,evaluation.evidence_digest,tuple(sorted(dispositions)))
