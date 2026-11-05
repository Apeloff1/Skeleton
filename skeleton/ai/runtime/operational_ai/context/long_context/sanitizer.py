"""Prompt-injection screening of untrusted source and tool text."""
from __future__ import annotations
import re
from .contracts import Span,ContextError

_PATTERNS=(re.compile(x,re.I) for x in (
    r'ignore (?:all|the) previous instructions',
    r'you (?:are|must) now (?:the |an? )?system',
    r'<\s*/?system\s*>',
    r'BEGIN [A-Z ]*PRIVATE KEY',
    r'\[INST\]',
))
_PATTERNS=tuple(_PATTERNS)

def suspicious(span:Span)->tuple[str,...]:
    if span.trust not in {'retrieved','tool_result'}:return ()
    return tuple(p.pattern for p in _PATTERNS if p.search(span.text))


def require_safe_evidence(span:Span,*,hard_fail:bool=True)->tuple[str,...]:
    flags=suspicious(span)
    if flags and hard_fail:raise ContextError('untrusted passage contains instruction injection indicators')
    return flags
