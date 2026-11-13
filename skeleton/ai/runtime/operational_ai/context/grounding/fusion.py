"""Reciprocal-rank fusion of independent offline retrieval modalities."""
from __future__ import annotations
from collections import defaultdict
from .documents import Passage,GroundingError


def reciprocal_rank_fusion(runs:tuple[tuple[Passage,...],...],*,k:int=60,
                           limit:int=16)->tuple[tuple[Passage,float],...]:
    if type(k) is not int or not 1<=k<=1000 or type(limit) is not int or not 1<=limit<=128:
        raise GroundingError('invalid rank-fusion budget')
    merged={};scores=defaultdict(float)
    for run in runs:
        if len(run)>2048:raise GroundingError('unbounded fusion input')
        seen=set()
        for rank,p in enumerate(run,1):
            if p.chunk_id in seen:continue
            if p.chunk_id in merged and merged[p.chunk_id]!=p:
                raise GroundingError('same chunk ID bound to different source bytes')
            seen.add(p.chunk_id);merged[p.chunk_id]=p;scores[p.chunk_id]+=1/(k+rank)
    ids=sorted(scores,key=lambda i:(-scores[i],i))[:limit]
    return tuple((merged[i],scores[i]) for i in ids)
