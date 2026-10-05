"""Citation graph evidence and analytics for VOL-212."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Mapping

class CitationGraphError(ValueError): pass

def _token(name:str,value:object)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>512: raise CitationGraphError(f"{name} must be non-empty normalized text")
    return value
def _sha(name:str,value:object)->str:
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value): raise CitationGraphError(f"{name} must be lowercase sha256")
    return value
def _digest(v:object)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class CitationNode:
    work_id:str; evidence_digest:str; year:int
    def __post_init__(self):
        object.__setattr__(self,"work_id",_token("work_id",self.work_id)); object.__setattr__(self,"evidence_digest",_sha("evidence_digest",self.evidence_digest))
        if isinstance(self.year,bool) or not isinstance(self.year,int) or not 1000<=self.year<=3000: raise CitationGraphError("year out of supported range")
    @property
    def digest(self)->str: return _digest({"work_id":self.work_id,"evidence_digest":self.evidence_digest,"year":self.year})

@dataclass(frozen=True,slots=True)
class CitationEdge:
    citing_work_id:str; cited_work_id:str; relation:str="cites"
    def __post_init__(self):
        object.__setattr__(self,"citing_work_id",_token("citing_work_id",self.citing_work_id)); object.__setattr__(self,"cited_work_id",_token("cited_work_id",self.cited_work_id))
        object.__setattr__(self,"relation",_token("relation",self.relation))
        if self.citing_work_id==self.cited_work_id: raise CitationGraphError("citation cannot self-reference")
    @property
    def key(self)->tuple[str,str,str]: return (self.citing_work_id,self.cited_work_id,self.relation)

@dataclass(frozen=True,slots=True)
class CitationGraph:
    graph_id:str; nodes:tuple[CitationNode,...]; edges:tuple[CitationEdge,...]
    def __post_init__(self):
        object.__setattr__(self,"graph_id",_token("graph_id",self.graph_id))
        if not self.nodes: raise CitationGraphError("citation graph requires nodes")
        ids=[n.work_id for n in self.nodes]
        if len(ids)!=len(set(ids)): raise CitationGraphError("citation node ids must be unique")
        known=set(ids); keys=[e.key for e in self.edges]
        if len(keys)!=len(set(keys)): raise CitationGraphError("citation edges must be unique")
        if any(e.citing_work_id not in known or e.cited_work_id not in known for e in self.edges): raise CitationGraphError("citation edge references unknown work")
        object.__setattr__(self,"nodes",tuple(sorted(self.nodes,key=lambda n:n.work_id))); object.__setattr__(self,"edges",tuple(sorted(self.edges,key=lambda e:e.key)))
    def inbound_counts(self)->Mapping[str,int]:
        counts={n.work_id:0 for n in self.nodes}
        for e in self.edges: counts[e.cited_work_id]+=1
        return dict(sorted(counts.items()))
    @property
    def digest(self)->str:
        return _digest({"graph_id":self.graph_id,"nodes":[n.digest for n in self.nodes],"edges":[list(e.key) for e in self.edges]})
