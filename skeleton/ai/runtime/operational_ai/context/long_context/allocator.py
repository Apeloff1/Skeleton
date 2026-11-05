"""Stable bounded evidence allocation without truncating trusted turns."""
from __future__ import annotations
from .contracts import Span,ContextError
from .budget import Window
from .tokens import TokenMeter
from .escape import quote_evidence


def allocate_evidence(evidence:list[Span],meter:TokenMeter,remaining:int,maximum:int=8)->tuple[Span,...]:
    if type(remaining) is not int or remaining<0 or not 0<=maximum<=64:
        raise ContextError('invalid evidence budget')
    accepted=[]
    for item in evidence:
        if item.trust not in {'retrieved','tool_result'}:raise ContextError('only untrusted evidence may be allocated')
        n=meter.count(quote_evidence(item))
        if n<=remaining and len(accepted)<maximum:
            accepted.append(item);remaining-=n
    return tuple(accepted)
