"""Preserve authoritative history order when adding retrieved material."""
from __future__ import annotations
from .contracts import Span,ContextError


def canonical_order(history:list[Span],evidence:list[Span])->tuple[Span,...]:
    names=set()
    for span in (*history,*evidence):
        if span.span_id in names:raise ContextError('duplicate span identity')
        names.add(span.span_id)
    if any(x.trust in {'retrieved','tool_result'} for x in history):
        raise ContextError('derived data cannot be authoritative history')
    if any(x.trust not in {'retrieved','tool_result'} for x in evidence):
        raise ContextError('instructional input cannot enter retrieval lane')
    return tuple(history)+tuple(sorted(evidence,key=lambda x:(x.span_id,x.revision)))
