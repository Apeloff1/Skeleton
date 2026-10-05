"""Dataset contamination fingerprint auditor for VOL-219."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re
from typing import Iterable

class ContaminationAuditError(ValueError): pass
_SPLITS=frozenset({"train","validation","test","benchmark"})

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise ContaminationAuditError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ContaminationAuditError(f"{n} must be lowercase sha256")
    return v
def normalize_text(text:str)->str:
    if not isinstance(text,str) or not text.strip(): raise ContaminationAuditError("text must be non-empty")
    return re.sub(r"\s+"," ",text.strip().lower())
def fingerprint_text(text:str)->str: return hashlib.sha256(normalize_text(text).encode()).hexdigest()
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ContentFingerprint:
    item_id:str; split:str; digest:str; normalized_length:int
    def __post_init__(self):
        object.__setattr__(self,"item_id",_token("item_id",self.item_id))
        split=_token("split",self.split)
        if split not in _SPLITS: raise ContaminationAuditError("unknown dataset split")
        object.__setattr__(self,"split",split); object.__setattr__(self,"digest",_sha("digest",self.digest))
        if isinstance(self.normalized_length,bool) or not isinstance(self.normalized_length,int) or self.normalized_length<=0: raise ContaminationAuditError("normalized_length must be positive")
    @classmethod
    def from_text(cls,item_id:str,split:str,text:str)->"ContentFingerprint":
        normalized=normalize_text(text); return cls(item_id,split,hashlib.sha256(normalized.encode()).hexdigest(),len(normalized))

@dataclass(frozen=True,slots=True)
class ContaminationFinding:
    training_item_id:str; evaluation_item_id:str; digest:str
    def __post_init__(self):
        object.__setattr__(self,"training_item_id",_token("training_item_id",self.training_item_id)); object.__setattr__(self,"evaluation_item_id",_token("evaluation_item_id",self.evaluation_item_id)); object.__setattr__(self,"digest",_sha("digest",self.digest))

@dataclass(frozen=True,slots=True)
class ContaminationAudit:
    audit_id:str; findings:tuple[ContaminationFinding,...]; clean:bool; sota_claim_allowed:bool=False
    def __post_init__(self):
        object.__setattr__(self,"audit_id",_token("audit_id",self.audit_id)); object.__setattr__(self,"findings",tuple(sorted(self.findings,key=lambda f:(f.training_item_id,f.evaluation_item_id))))
        if self.clean!=(len(self.findings)==0): raise ContaminationAuditError("clean must match findings")
        if self.sota_claim_allowed is not False: raise ContaminationAuditError("contamination audit cannot authorize SOTA claims")
    @property
    def digest(self)->str: return _digest({"audit_id":self.audit_id,"findings":[{"train":f.training_item_id,"eval":f.evaluation_item_id,"digest":f.digest} for f in self.findings],"clean":self.clean,"sota_claim_allowed":False})

def audit_contamination(*,audit_id:str,items:Iterable[ContentFingerprint])->ContaminationAudit:
    rows=tuple(items); train=[x for x in rows if x.split=="train"]; evaluation=[x for x in rows if x.split in {"validation","test","benchmark"}]
    findings=[]
    for left in train:
        for right in evaluation:
            if left.digest==right.digest: findings.append(ContaminationFinding(left.item_id,right.item_id,left.digest))
    return ContaminationAudit(audit_id,tuple(findings),not findings)
