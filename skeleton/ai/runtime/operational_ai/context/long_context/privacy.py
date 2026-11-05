"""Controlled context disclosure checks before sending data to a model."""
from __future__ import annotations
from .contracts import Span,ContextError


def public_only(spans:tuple[Span,...],rights:dict[str,str])->tuple[Span,...]:
    selected=[]
    for s in spans:
        label=rights.get(s.span_id)
        if label not in {'public','approved-local'}:
            raise ContextError('source rights not admitted for model projection')
        selected.append(s)
    return tuple(selected)
