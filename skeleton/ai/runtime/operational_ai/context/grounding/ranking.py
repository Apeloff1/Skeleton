"""Deterministic hybrid lexical reranking, redundancy control and trust penalty."""
from __future__ import annotations
from dataclasses import dataclass
import math
from .documents import Passage,GroundingError
from .query import words,overlap_score

@dataclass(frozen=True,slots=True)
class RankedHit:
    passage:Passage
    score:float
    lexical_score:float
    trust_penalty:float


def _redundancy(a:Passage,b:Passage)->float:
    if a.doc_id!=b.doc_id:return 0.0
    overlap=max(0,min(a.end,b.end)-max(a.start,b.start))
    return overlap/max(1,min(a.end-a.start,b.end-b.start))


def rerank(query:str,hits:tuple[tuple[Passage,float],...],*,limit:int=8,
           max_per_document:int=3,lambda_mmr:float=0.72)->tuple[RankedHit,...]:
    if (type(limit) is not int or not 1<=limit<=64
        or type(max_per_document) is not int or not 1<=max_per_document<=32
        or not isinstance(lambda_mmr,(int,float)) or not 0<=lambda_mmr<=1):
        raise GroundingError('invalid reranking limits')
    candidates=[]
    for passage,bm25 in hits:
        if not isinstance(passage,Passage) or not math.isfinite(bm25):
            raise GroundingError('corrupt search score')
        lexical=overlap_score(query,passage.body)
        trust=0.3 if passage.trust=='untrusted-reference' else 0.0
        # Lower BM25 is better. Normalize before deterministic score fusion.
        bm=1.0/(1.0+abs(bm25))
        score=0.65*lexical+0.35*bm-trust
        candidates.append(RankedHit(passage,score,lexical,trust))
    selected=[];counts={};unselected={hit.passage.chunk_id:hit for hit in candidates}
    while unselected and len(selected)<limit:
        ranked=[]
        for hit in unselected.values():
            if counts.get(hit.passage.doc_id,0)>=max_per_document:continue
            redundancy=max((_redundancy(hit.passage,x.passage) for x in selected),default=0.0)
            mmr=lambda_mmr*hit.score-(1-lambda_mmr)*redundancy
            ranked.append((mmr,hit.score,hit.passage.chunk_id,hit))
        if not ranked:break
        ranked.sort(key=lambda x:(-x[0],-x[1],x[2]))
        hit=ranked[0][3]
        selected.append(hit)
        counts[hit.passage.doc_id]=counts.get(hit.passage.doc_id,0)+1
        del unselected[hit.passage.chunk_id]
    return tuple(selected)
