"""Calibrated passage fusion and source-identity-bound diverse results."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import identifier,sha,number,integer,refuse
from .math import reciprocal_rank_fusion
@dataclass(frozen=True,slots=True)
class RankedSource:
    source_id:str
    scope:str
    source_sha256:str
    lexical:float
    dense:float
    freshness:float
    rights_approved:bool
    def __post_init__(self):
        identifier(self.source_id);identifier(self.scope);sha(self.source_sha256)
        for v in (self.lexical,self.dense,self.freshness):
            number(v,minimum=0,maximum=1)
        if type(self.rights_approved) is not bool:
            refuse("external content rights approval must be explicit")
def rank(sources,*,scope,weights=(0.55,0.35,0.10),limit=20,min_score=0.01):
    identifier(scope);integer(limit,minimum=1,maximum=1000)
    min_score=number(min_score,minimum=0,maximum=1)
    if type(sources) not in (tuple,list) or len(sources)>10000:
        refuse("source ranking batch ceiling")
    from .math import normalize_weights
    a,b,c=normalize_weights(weights)
    seen=set();results=[]
    for source in sources:
        if type(source) is not RankedSource:refuse("untyped provenance source")
        if source.source_id in seen:refuse("duplicate ranked source")
        seen.add(source.source_id)
        if source.scope!=scope or not source.rights_approved:continue
        score=a*source.lexical+b*source.dense+c*source.freshness
        if score>=min_score:results.append((source.source_id,score,source.source_sha256))
    results.sort(key=lambda x:(-x[1],x[0]))
    return tuple(results[:limit])
