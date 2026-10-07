"""Promotion, quarantine, policy receipts and host-level adaptive controls."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,asdict
from urllib.parse import urlsplit
from .core import CrawlDocument
from .research import EvidenceSet

@dataclass(frozen=True)
class PromotionDecision:
    decision_id:str; content_hash:str; action:str; reasons:tuple[str,...]; decided_at:float
    assurance_score:float; provenance_schema:str|None
    def receipt(self)->dict[str,object]:
        return {"schema":"skeleton.ai.crawl.promotion.v1",**asdict(self)}

class PromotionGate:
    def __init__(self,min_source_score=.45,min_assurance=.45):
        self.min_source_score=min_source_score;self.min_assurance=min_assurance
    def decide(self,doc:CrawlDocument,evidence:EvidenceSet,*,now:float)->PromotionDecision:
        reasons=[]
        assurance=evidence.assurance(now=now)
        schema=str(doc.provenance.get("schema","")) or None
        if doc.source_score < self.min_source_score:reasons.append("low_source_score")
        if float(assurance["score"]) < self.min_assurance:reasons.append("low_assurance")
        if not assurance["sufficient"]:reasons.append("insufficient_corroboration")
        if not schema:reasons.append("missing_provenance")
        action="promote" if not reasons else "quarantine"
        did=hashlib.sha256(f"{doc.content_hash}:{action}:{','.join(reasons)}".encode()).hexdigest()
        return PromotionDecision(did,doc.content_hash,action,tuple(reasons),now,float(assurance["score"]),schema)

@dataclass
class HostHealth:
    successes:int=0; failures:int=0; bytes:int=0
    def quality(self)->float:return (self.successes+1)/(self.successes+self.failures+2)

class HostBudgetController:
    def __init__(self,base_requests=20,min_requests=2,max_requests=100):
        self.base=base_requests;self.minimum=min_requests;self.maximum=max_requests;self.health={}
    def observe(self,url:str,*,success:bool,byte_count:int=0):
        host=(urlsplit(url).hostname or "").lower()
        h=self.health.setdefault(host,HostHealth())
        h.successes+=int(success);h.failures+=int(not success);h.bytes+=max(0,byte_count)
    def allowance(self,host:str)->int:
        h=self.health.get(host.lower(),HostHealth())
        scaled=round(self.base*(.5+h.quality()))
        return max(self.minimum,min(self.maximum,scaled))
