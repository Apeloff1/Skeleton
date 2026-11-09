"""FLGB-17 adversarial forge, rights-clean-room, and promotion contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Sequence
MAX_ID=256; MAX_SCORE=1000000; MAX_CYCLES=10000
class ForgeContractError(ValueError): pass
def _int(v): return isinstance(v,int) and not isinstance(v,bool)
def req_id(v,n):
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID: raise ForgeContractError(f"invalid {n}")
    return v
def req_digest(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ForgeContractError(f"invalid {n}")
    return v
def dig(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()
    except (TypeError,ValueError) as exc: raise ForgeContractError("non-canonical value") from exc
    return sha256(raw).hexdigest()
@dataclass(frozen=True)
class RivalProposal:
    proposal_id:str; round_index:int; artifact_digest:str; rationale_digest:str; source_provenance_digest:str
    def __post_init__(self):
        req_id(self.proposal_id,"proposal_id"); req_digest(self.artifact_digest,"artifact_digest"); req_digest(self.rationale_digest,"rationale_digest"); req_digest(self.source_provenance_digest,"source_provenance_digest")
        if not _int(self.round_index) or self.round_index<0: raise ForgeContractError("invalid round_index")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class RivalChallenge:
    challenge_id:str; proposal_digest:str; defect_digests:tuple[str,...]; severity_ppm:int; independent_agent_id:str
    def __post_init__(self):
        req_id(self.challenge_id,"challenge_id"); req_digest(self.proposal_digest,"proposal_digest"); req_id(self.independent_agent_id,"independent_agent_id")
        ds=tuple(sorted(self.defect_digests))
        if len(set(ds))!=len(ds): raise ForgeContractError("duplicate defect")
        for d in ds: req_digest(d,"defect_digest")
        object.__setattr__(self,"defect_digests",ds)
        if not _int(self.severity_ppm) or not 0<=self.severity_ppm<=MAX_SCORE: raise ForgeContractError("invalid severity")
@dataclass(frozen=True)
class RivalVerification:
    verification_id:str; proposal_digest:str; challenge_digest:str; quality_ppm:int; risk_ppm:int; rights_clear:bool; verifier_id:str; evidence_digest:str
    def __post_init__(self):
        req_id(self.verification_id,"verification_id"); req_digest(self.proposal_digest,"proposal_digest"); req_digest(self.challenge_digest,"challenge_digest"); req_id(self.verifier_id,"verifier_id"); req_digest(self.evidence_digest,"evidence_digest")
        for n in ("quality_ppm","risk_ppm"):
            v=getattr(self,n)
            if not _int(v) or not 0<=v<=MAX_SCORE: raise ForgeContractError(f"invalid {n}")
        if not isinstance(self.rights_clear,bool): raise ForgeContractError("rights_clear must be boolean")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class ForgeCyclePlan:
    tier:str; cycles:int; minimum_delta_ppm:int; maximum_risk_ppm:int
    def __post_init__(self):
        expected={"forge-100":100,"forge-1000":1000,"forge-10000":10000}
        if self.tier not in expected or self.cycles!=expected[self.tier]: raise ForgeContractError("tier/cycle mismatch")
        if not _int(self.minimum_delta_ppm) or not 0<=self.minimum_delta_ppm<=MAX_SCORE or not _int(self.maximum_risk_ppm) or not 0<=self.maximum_risk_ppm<=MAX_SCORE: raise ForgeContractError("invalid forge threshold")
def forge_100(minimum_delta_ppm:int,maximum_risk_ppm:int): return ForgeCyclePlan("forge-100",100,minimum_delta_ppm,maximum_risk_ppm)
def forge_1000(minimum_delta_ppm:int,maximum_risk_ppm:int): return ForgeCyclePlan("forge-1000",1000,minimum_delta_ppm,maximum_risk_ppm)
def forge_10000(minimum_delta_ppm:int,maximum_risk_ppm:int): return ForgeCyclePlan("forge-10000",10000,minimum_delta_ppm,maximum_risk_ppm)
@dataclass(frozen=True)
class QualityDelta:
    baseline_digest:str; candidate_digest:str; baseline_score_ppm:int; candidate_score_ppm:int; evidence_digest:str
    def __post_init__(self):
        req_digest(self.baseline_digest,"baseline_digest"); req_digest(self.candidate_digest,"candidate_digest"); req_digest(self.evidence_digest,"evidence_digest")
        for n in ("baseline_score_ppm","candidate_score_ppm"):
            v=getattr(self,n)
            if not _int(v) or not 0<=v<=MAX_SCORE: raise ForgeContractError(f"invalid {n}")
    @property
    def delta_ppm(self): return self.candidate_score_ppm-self.baseline_score_ppm
@dataclass(frozen=True)
class StopPolicy:
    max_cycles:int; minimum_delta_ppm:int; patience:int; maximum_risk_ppm:int
    def __post_init__(self):
        if not _int(self.max_cycles) or not 1<=self.max_cycles<=MAX_CYCLES or not _int(self.patience) or not 1<=self.patience<=self.max_cycles: raise ForgeContractError("invalid stop budget")
        for n in ("minimum_delta_ppm","maximum_risk_ppm"):
            v=getattr(self,n)
            if not _int(v) or not 0<=v<=MAX_SCORE: raise ForgeContractError(f"invalid {n}")
    def should_stop(self,cycle:int,stale_cycles:int,delta_ppm:int,risk_ppm:int)->bool:
        if not all(_int(v) for v in (cycle,stale_cycles,delta_ppm,risk_ppm)): raise ForgeContractError("invalid stop inputs")
        return cycle>=self.max_cycles or stale_cycles>=self.patience or risk_ppm>self.maximum_risk_ppm or delta_ppm<self.minimum_delta_ppm
@dataclass(frozen=True)
class RightsFingerprint:
    artifact_digest:str; fingerprint_digest:str; corpus_version_digest:str; threshold_ppm:int
    def __post_init__(self):
        req_digest(self.artifact_digest,"artifact_digest"); req_digest(self.fingerprint_digest,"fingerprint_digest"); req_digest(self.corpus_version_digest,"corpus_version_digest")
        if not _int(self.threshold_ppm) or not 0<=self.threshold_ppm<=MAX_SCORE: raise ForgeContractError("invalid rights threshold")
@dataclass(frozen=True)
class SourceProvenance:
    source_id:str; source_digest:str; rights_digest:str; acquisition_digest:str; transformation_chain_digest:str
    def __post_init__(self): req_id(self.source_id,"source_id"); req_digest(self.source_digest,"source_digest"); req_digest(self.rights_digest,"rights_digest"); req_digest(self.acquisition_digest,"acquisition_digest"); req_digest(self.transformation_chain_digest,"transformation_chain_digest")
    @property
    def digest(self): return dig(self.__dict__)
@dataclass(frozen=True)
class CleanRoomTransformation:
    transformation_id:str; source_fingerprint_digest:str; instruction_digest:str; output_digest:str; similarity_ppm:int; verifier_digest:str
    def __post_init__(self):
        req_id(self.transformation_id,"transformation_id"); req_digest(self.source_fingerprint_digest,"source_fingerprint_digest"); req_digest(self.instruction_digest,"instruction_digest"); req_digest(self.output_digest,"output_digest"); req_digest(self.verifier_digest,"verifier_digest")
        if not _int(self.similarity_ppm) or not 0<=self.similarity_ppm<=MAX_SCORE: raise ForgeContractError("invalid similarity")
    def clears(self,maximum_similarity_ppm:int)->bool:
        if not _int(maximum_similarity_ppm) or not 0<=maximum_similarity_ppm<=MAX_SCORE: raise ForgeContractError("invalid similarity threshold")
        return self.similarity_ppm<=maximum_similarity_ppm
@dataclass(frozen=True)
class PromotionCandidate:
    candidate_id:str; artifact_digest:str; quality_ppm:int; risk_ppm:int; rights_clear:bool; provenance_digest:str; verification_digest:str
    def __post_init__(self):
        req_id(self.candidate_id,"candidate_id"); req_digest(self.artifact_digest,"artifact_digest"); req_digest(self.provenance_digest,"provenance_digest"); req_digest(self.verification_digest,"verification_digest")
        for n in ("quality_ppm","risk_ppm"):
            v=getattr(self,n)
            if not _int(v) or not 0<=v<=MAX_SCORE: raise ForgeContractError(f"invalid {n}")
        if not isinstance(self.rights_clear,bool): raise ForgeContractError("rights_clear must be boolean")
def arbitrate_promotion(candidates:Sequence[PromotionCandidate],minimum_quality_ppm:int,maximum_risk_ppm:int)->PromotionCandidate:
    if not _int(minimum_quality_ppm) or not _int(maximum_risk_ppm): raise ForgeContractError("invalid arbitration thresholds")
    ids=[c.candidate_id for c in candidates]
    if len(set(ids))!=len(ids): raise ForgeContractError("duplicate candidate")
    eligible=[c for c in candidates if c.rights_clear and c.quality_ppm>=minimum_quality_ppm and c.risk_ppm<=maximum_risk_ppm]
    if not eligible: raise ForgeContractError("no promotable candidate")
    return sorted(eligible,key=lambda c:(-c.quality_ppm,c.risk_ppm,c.candidate_id))[0]
