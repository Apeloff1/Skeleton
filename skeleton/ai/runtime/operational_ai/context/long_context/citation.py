"""Exact cited evidence identifiers, no fabricated source links."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import Span,ContextError

@dataclass(frozen=True,slots=True)
class EvidenceCitation:
    span_id:str
    digest:str
    start:int
    end:int


def require_citation(citation:EvidenceCitation,sources:tuple[Span,...])->Span:
    for source in sources:
        if (source.span_id==citation.span_id and source.digest==citation.digest and
            type(citation.start) is int and type(citation.end) is int and
            0<=citation.start<=citation.end<=len(source.text)):
            return source
    raise ContextError('citation not present in admitted source set')
