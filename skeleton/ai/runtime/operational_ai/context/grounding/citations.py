"""Post-generation source citations: verify exact document revision and offsets."""
from __future__ import annotations
from dataclasses import dataclass
import re
from .documents import Passage,GroundingError
from .index import GroundingIndex

_CITE=re.compile(r'\[source:([A-Za-z0-9][A-Za-z0-9_-]{0,127}):([0-9]{1,9})-([0-9]{1,9})\]')

@dataclass(frozen=True,slots=True)
class Citation:
    doc_id:str
    start:int
    end:int
    token:str


def parse_citations(answer:str,*,maximum:int=128)->tuple[Citation,...]:
    if not isinstance(answer,str) or len(answer.encode('utf8'))>262144:
        raise GroundingError('answer too large for bounded citation check')
    results=[]
    for match in _CITE.finditer(answer):
        results.append(Citation(match[1],int(match[2]),int(match[3]),match[0]))
        if len(results)>maximum:raise GroundingError('citation count exceeded')
    return tuple(results)


def verify_citations(answer:str,hits:tuple[Passage,...],index:GroundingIndex,
                     tenant:str,user:str,*,require_any:bool=False)->tuple[Citation,...]:
    citations=parse_citations(answer)
    if require_any and not citations:
        raise GroundingError('answer without required source citations')
    for cite in citations:
        matched=False
        for passage in hits:
            if (passage.doc_id==cite.doc_id and passage.start<=cite.start<cite.end<=passage.end
                and index.verify(tenant,user,passage)):
                matched=True;break
        if not matched:
            raise GroundingError(f'unsupported or stale citation: {cite.token}')
    return citations
