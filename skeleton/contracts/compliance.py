"""Evidence-bound compliance contracts for VOL-088."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable

COMPLIANCE_SCHEMA="skeleton.contracts.compliance.v1"
_TOKEN=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
class ComplianceError(ValueError): pass
class RequirementDisposition(str,Enum):
    REQUIRED="required"
    NOT_APPLICABLE="not_applicable"
class EvidenceResult(str,Enum):
    PASS="pass"
    FAIL="fail"
class ControlStatus(str,Enum):
    SATISFIED="satisfied"
    FAILED="failed"
    EVIDENCE_MISSING="evidence_missing"
    EVIDENCE_STALE="evidence_stale"
    NOT_APPLICABLE="not_applicable"
def _tok(v,field):
    if not isinstance(v,str) or not _TOKEN.fullmatch(v): raise ComplianceError(f"{field} must be canonical token")
    return v
def _txt(v,field):
    if not isinstance(v,str) or v!=v.strip() or not v or len(v)>4096: raise ComplianceError(f"{field} must be bounded text")
    return v
def _time(v,field):
    if not isinstance(v,datetime) or v.tzinfo is None: raise ComplianceError(f"{field} must be timezone-aware")
    return v.astimezone(timezone.utc)
def _digest(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    except (TypeError,ValueError) as exc: raise ComplianceError("value must be deterministic JSON") from exc
    return sha256(raw).hexdigest()
@dataclass(frozen=True,slots=True)
class ComplianceRequirement:
    requirement_id:str; source:str; statement:str; owner:str
    disposition:RequirementDisposition=RequirementDisposition.REQUIRED
    applicability_reason:str="in-scope"
    def __post_init__(self):
        for f in ("requirement_id","source","owner"): object.__setattr__(self,f,_tok(getattr(self,f),f))
        object.__setattr__(self,"statement",_txt(self.statement,"statement")); object.__setattr__(self,"applicability_reason",_txt(self.applicability_reason,"applicability_reason"))
        if not isinstance(self.disposition,RequirementDisposition): raise ComplianceError("invalid disposition")
    @property
    def digest(self): return _digest([COMPLIANCE_SCHEMA,self.requirement_id,self.source,self.statement,self.owner,self.disposition.value,self.applicability_reason])
@dataclass(frozen=True,slots=True)
class ComplianceControl:
    control_id:str; owner:str; requirement_ids:tuple[str,...]; evidence_ttl_seconds:int; description:str
    def __post_init__(self):
        object.__setattr__(self,"control_id",_tok(self.control_id,"control_id")); object.__setattr__(self,"owner",_tok(self.owner,"owner"))
        if not isinstance(self.requirement_ids,tuple) or not self.requirement_ids or len(self.requirement_ids)>256: raise ComplianceError("bounded requirement tuple required")
        ids=tuple(sorted(_tok(x,"requirement_id") for x in self.requirement_ids))
        if len(ids)!=len(set(ids)): raise ComplianceError("duplicate requirement")
        object.__setattr__(self,"requirement_ids",ids)
        if isinstance(self.evidence_ttl_seconds,bool) or not isinstance(self.evidence_ttl_seconds,int) or not 1<=self.evidence_ttl_seconds<=31536000: raise ComplianceError("invalid evidence ttl")
        object.__setattr__(self,"description",_txt(self.description,"description"))
    @property
    def digest(self): return _digest([COMPLIANCE_SCHEMA,self.control_id,self.owner,self.requirement_ids,self.evidence_ttl_seconds,self.description])
@dataclass(frozen=True,slots=True)
class ComplianceEvidence:
    evidence_id:str; control_id:str; control_digest:str; owner:str; artifact_digest:str; observed_at:datetime; result:EvidenceResult
    def __post_init__(self):
        for f in ("evidence_id","control_id","owner"): object.__setattr__(self,f,_tok(getattr(self,f),f))
        for f in ("control_digest","artifact_digest"):
            if not isinstance(getattr(self,f),str) or not _SHA.fullmatch(getattr(self,f)): raise ComplianceError(f"{f} must be sha256")
        object.__setattr__(self,"observed_at",_time(self.observed_at,"observed_at"))
        if not isinstance(self.result,EvidenceResult): raise ComplianceError("invalid evidence result")
    @property
    def digest(self): return _digest([COMPLIANCE_SCHEMA,self.evidence_id,self.control_id,self.control_digest,self.owner,self.artifact_digest,self.observed_at.isoformat(),self.result.value])
@dataclass(frozen=True,slots=True)
class ControlAssessment:
    control_id:str; status:ControlStatus; evidence_digest:str|None; reason:str
@dataclass(frozen=True,slots=True)
class ComplianceAssessment:
    registry_digest:str; assessed_at:datetime; controls:tuple[ControlAssessment,...]
    @property
    def compliant(self): return all(x.status in (ControlStatus.SATISFIED,ControlStatus.NOT_APPLICABLE) for x in self.controls)
    @property
    def digest(self): return _digest([COMPLIANCE_SCHEMA,self.registry_digest,self.assessed_at.isoformat(),[(x.control_id,x.status.value,x.evidence_digest,x.reason) for x in self.controls]])
class ComplianceRegistry:
    def __init__(self,requirements:Iterable[ComplianceRequirement],controls:Iterable[ComplianceControl]):
        self.requirements=tuple(sorted(requirements,key=lambda x:x.requirement_id)); self.controls=tuple(sorted(controls,key=lambda x:x.control_id))
        if not self.requirements or not self.controls: raise ComplianceError("requirements and controls required")
        if len({x.requirement_id for x in self.requirements})!=len(self.requirements) or len({x.control_id for x in self.controls})!=len(self.controls): raise ComplianceError("duplicate registry id")
        known={x.requirement_id for x in self.requirements}; covered=set()
        for c in self.controls:
            if set(c.requirement_ids)-known: raise ComplianceError("control references unknown requirement")
            covered.update(c.requirement_ids)
        required={x.requirement_id for x in self.requirements if x.disposition is RequirementDisposition.REQUIRED}
        if required-covered: raise ComplianceError("required requirement lacks control")
    @property
    def digest(self): return _digest([COMPLIANCE_SCHEMA,[x.digest for x in self.requirements],[x.digest for x in self.controls]])
    def assess(self,evidence:Iterable[ComplianceEvidence],*,at:datetime):
        now=_time(at,"assessment time"); by={}
        for e in evidence: by.setdefault(e.control_id,[]).append(e)
        if set(by)-{c.control_id for c in self.controls}: raise ComplianceError("evidence references unknown control")
        req={r.requirement_id:r for r in self.requirements}; out=[]
        for c in self.controls:
            if not any(req[r].disposition is RequirementDisposition.REQUIRED for r in c.requirement_ids): out.append(ControlAssessment(c.control_id,ControlStatus.NOT_APPLICABLE,None,"all linked requirements are not applicable")); continue
            valid=[e for e in by.get(c.control_id,[]) if e.control_digest==c.digest and e.owner==c.owner and e.observed_at<=now]
            if not valid: out.append(ControlAssessment(c.control_id,ControlStatus.EVIDENCE_MISSING,None,"no identity-bound evidence")); continue
            latest=max(valid,key=lambda e:(e.observed_at,e.digest)); age=(now-latest.observed_at).total_seconds()
            if age>c.evidence_ttl_seconds: status,reason=ControlStatus.EVIDENCE_STALE,"evidence exceeded freshness policy"
            elif latest.result is EvidenceResult.FAIL: status,reason=ControlStatus.FAILED,"latest evidence reports failure"
            else: status,reason=ControlStatus.SATISFIED,"fresh identity-bound evidence passed"
            out.append(ControlAssessment(c.control_id,status,latest.digest,reason))
        return ComplianceAssessment(self.digest,now,tuple(out))
