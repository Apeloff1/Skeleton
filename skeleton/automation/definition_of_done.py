"""Evidence-derived Definition of Done for VOL-110."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class DoDError(ValueError):pass
class EvidenceKind(str,Enum): IMPLEMENTATION="implementation"; TEST="test"; FAILURE="failure"; RECOVERY="recovery"; OBSERVABILITY="observability"; ROLLBACK="rollback"; OWNERSHIP="ownership"; VERIFICATION="verification"
class Impact(str,Enum): LOW="low"; MEDIUM="medium"; HIGH="high"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise DoDError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise DoDError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class DoDRequirement:
 requirement_id:str;kind:EvidenceKind;minimum_impact:Impact
 def __post_init__(self):object.__setattr__(self,"requirement_id",_id(self.requirement_id,"requirement_id"))
@dataclass(frozen=True,slots=True)
class CompletionEvidence:
 evidence_id:str;kind:EvidenceKind;artifact_digest:str;actor_id:str
 def __post_init__(self):
  object.__setattr__(self,"evidence_id",_id(self.evidence_id,"evidence_id"));_sha(self.artifact_digest,"artifact_digest");object.__setattr__(self,"actor_id",_id(self.actor_id,"actor_id"))
@dataclass(frozen=True,slots=True)
class DefinitionOfDone:
 policy_id:str;requirements:tuple[DoDRequirement,...]
 def __post_init__(self):
  object.__setattr__(self,"policy_id",_id(self.policy_id,"policy_id"))
  if not self.requirements:raise DoDError("DoD requirements required")
 def required_kinds(self,impact):
  rank={Impact.LOW:0,Impact.MEDIUM:1,Impact.HIGH:2};return frozenset(r.kind for r in self.requirements if rank[impact]>=rank[r.minimum_impact])
 def evaluate(self,impact,evidence,implementer_id):
  implementer_id=_id(implementer_id,"implementer_id");required=self.required_kinds(impact);by_kind={e.kind:e for e in evidence}
  missing=required-set(by_kind)
  if missing:return False,tuple(sorted(k.value for k in missing))
  verification=by_kind.get(EvidenceKind.VERIFICATION)
  if EvidenceKind.VERIFICATION in required and verification.actor_id==implementer_id:return False,("verification_not_independent",)
  return True,()
def canonical_policy():
 return DefinitionOfDone("DOD.CANONICAL",(
  DoDRequirement("REQ.IMPLEMENTATION",EvidenceKind.IMPLEMENTATION,Impact.LOW),
  DoDRequirement("REQ.TEST",EvidenceKind.TEST,Impact.LOW),
  DoDRequirement("REQ.OWNERSHIP",EvidenceKind.OWNERSHIP,Impact.LOW),
  DoDRequirement("REQ.FAILURE",EvidenceKind.FAILURE,Impact.MEDIUM),
  DoDRequirement("REQ.OBSERVABILITY",EvidenceKind.OBSERVABILITY,Impact.MEDIUM),
  DoDRequirement("REQ.RECOVERY",EvidenceKind.RECOVERY,Impact.HIGH),
  DoDRequirement("REQ.ROLLBACK",EvidenceKind.ROLLBACK,Impact.HIGH),
  DoDRequirement("REQ.VERIFICATION",EvidenceKind.VERIFICATION,Impact.HIGH),
 ))
