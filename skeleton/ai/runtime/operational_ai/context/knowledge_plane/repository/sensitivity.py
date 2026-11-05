"""Deliberately conservative accidental-secret gate on AI-indexable source."""
from __future__ import annotations
import re
from .contracts import GitSourceError

_PROHIBITED=(
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(rb'gh[pousr]_[a-zA-Z0-9]{24,}'),
    re.compile(rb'github_pat_[a-zA-Z0-9_]{24,}'),
    re.compile(rb'AKIA[0-9A-Z]{16}'),
    re.compile(rb'(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*["\']?[a-z0-9_./+\-]{24,}'),
)


def require_publicly_indexable(raw:bytes)->None:
    if type(raw)is not bytes:
        raise GitSourceError('source bytes required')
    for pattern in _PROHIBITED:
        if pattern.search(raw):
            raise GitSourceError('potential secret in source: fail closed without exposing bytes')
