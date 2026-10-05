from dataclasses import dataclass
import math
@dataclass(frozen=True)
class SourceIdentity: source_id:str; owner:str
@dataclass(frozen=True)
class TrustEvidence: evidence_id:str; domain:str; valid_until:int
@dataclass(frozen=True)
class SourceTrust: source:SourceIdentity; claim_scope:str; score:float; evidence:tuple[TrustEvidence,...]
def trusted_for(t,domain,now):
 if not t.source.source_id or not t.source.owner or not t.claim_scope:raise ValueError("source trust identity/scope required")
 if isinstance(t.score,bool) or not isinstance(t.score,(int,float)) or not math.isfinite(t.score) or not 0<=t.score<=1:raise ValueError("invalid trust score")
 return t.score>=.5 and any(e.evidence_id and e.domain==domain and now<=e.valid_until for e in t.evidence)
def as_context(t,content):return {"content":content,"source":t.source.source_id,"instruction_authority":False}
