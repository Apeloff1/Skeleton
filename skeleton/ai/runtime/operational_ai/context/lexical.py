"""Deterministic bounded lexical retrieval, independent from model authority."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import math
import re
from typing import Iterable
from ..authority.canonical import ContractViolation, require_small_text
from .sources import Source

TOKEN = re.compile(r"[\w'-]{2,40}",re.UNICODE)
MAX_DOCUMENTS = 2048


def tokenize(text:str) -> list[str]:
    return [x.lower() for x in TOKEN.findall(text[:64_000])]


@dataclass(frozen=True, slots=True)
class Hit:
    source_id: str
    score: float
    start: int
    end: int
    body: str
    sha256: str
    trust: str
    origin: str
    rights: str


class LexicalIndex:
    def __init__(self,sources:Iterable[Source]=()):
        self._sources: dict[str,Source]={}
        for source in sources:
            self.add(source)

    def add(self,source:Source) -> None:
        if not isinstance(source,Source) or len(self._sources)>=MAX_DOCUMENTS and source.source_id not in self._sources:
            raise ContractViolation("evidence source capacity exceeded")
        existing=self._sources.get(source.source_id)
        if existing is not None and source.revision<=existing.revision:
            raise ContractViolation("evidence revision must advance")
        self._sources[source.source_id]=source

    def remove(self,source_id:str)->None:
        self._sources.pop(source_id,None)

    def query(self,question:str,*,tenant:str,user:str,limit:int=8,
              max_passage:int=2048) -> tuple[Hit,...]:
        require_small_text(question,field="query",maximum=4096)
        if type(limit) is not int or not 1<=limit<=32:
            raise ContractViolation("invalid retrieval count")
        if type(max_passage) is not int or not 128<=max_passage<=8192:
            raise ContractViolation("invalid passage budget")
        terms=tuple(dict.fromkeys(tokenize(question)))
        if not terms:
            return ()
        scoped=sorted((s for s in self._sources.values()
                       if s.owner_tenant==tenant and s.owner_user==user),
                      key=lambda s:s.source_id)
        if not scoped:
            return ()
        postings={s.source_id:Counter(tokenize(s.body)) for s in scoped}
        docs=len(scoped)
        frequency={term:sum(int(postings[s.source_id][term]>0) for s in scoped) for term in terms}
        ranked=[]
        for source in scoped:
            found=postings[source.source_id]
            score=sum((1+math.log1p(found[term]))*math.log1p((docs+1)/(frequency[term]+1))
                      for term in terms if found[term])
            if score<=0:
                continue
            lower=source.body.lower()
            anchors=[lower.find(term) for term in terms if lower.find(term)>=0]
            anchor=min(anchors) if anchors else 0
            start=max(0,anchor-max_passage//4)
            end=min(len(source.body),start+max_passage)
            chunk=source.body[start:end]
            ranked.append(Hit(source.source_id,round(score,8),start,end,chunk,
                              source.digest,source.trust,source.origin,source.rights))
        return tuple(sorted(ranked,key=lambda h:(-h.score,h.source_id))[:limit])

    def __len__(self)->int:
        return len(self._sources)
