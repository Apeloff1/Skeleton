"""Detect conflicting revisions and trust changes before projecting context."""
from __future__ import annotations
from .contracts import Span,ContextError


def latest_unique(spans:list[Span])->tuple[Span,...]:
    winners:dict[str,Span]={}
    for item in spans:
        old=winners.get(item.span_id)
        if old and old.trust!=item.trust:raise ContextError('span trust changed')
        if old and old.revision==item.revision and old.digest!=item.digest:
            raise ContextError('same-revision conflicting source')
        if old is None or item.revision>old.revision:winners[item.span_id]=item
    return tuple(winners[k] for k in sorted(winners))
