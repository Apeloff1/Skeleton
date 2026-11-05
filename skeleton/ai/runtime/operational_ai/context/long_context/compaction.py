"""Loss-aware caller-provided history projections, never silent deletion."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .contracts import Span,ContextError

@dataclass(frozen=True,slots=True)
class LossReceipt:
    input_spans:tuple[str,...]
    retained_spans:tuple[str,...]
    omitted_spans:tuple[str,...]
    input_digest:str
    explicit_approval:bool


def select_history(history:list[Span],retained_ids:set[str],*,approved:bool=False)->tuple[tuple[Span,...],LossReceipt]:
    if not approved:raise ContextError('history omission must be explicitly approved')
    if any(s.trust=='system' and s.span_id not in retained_ids for s in history):
        raise ContextError('cannot compact away system policy')
    if len(retained_ids)!=len(set(retained_ids)) or not retained_ids.issubset({s.span_id for s in history}):
        raise ContextError('invalid retention selection')
    keep=tuple(s for s in history if s.span_id in retained_ids)
    drop=tuple(s.span_id for s in history if s.span_id not in retained_ids)
    digest=sha256(''.join(s.digest for s in history).encode()).hexdigest()
    return keep,LossReceipt(tuple(s.span_id for s in history),tuple(s.span_id for s in keep),drop,digest,approved)
