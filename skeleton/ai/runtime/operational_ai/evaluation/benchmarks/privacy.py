"""Measured privacy heuristics, redaction required but never absolute guarantees."""
from __future__ import annotations
from dataclasses import dataclass
import re
from .dataset import EvalError

_PATTERNS={
 'private-key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'bearer':re.compile(r'(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/-]{16,}'),
 'api-token':re.compile(r'(?i)\b(?:api[_-]?key|access[_-]?token)\s*[:=]\s*[A-Za-z0-9._-]{24,}'),
 'cloud-secret':re.compile(r'(?i)\b(?:aws_secret_access_key|secret_access_key)\s*[:=]\s*\S{16,}'),
}
@dataclass(frozen=True,slots=True)
class PrivacyFinding:
    category:str
    start:int
    end:int


def inspect_answer(text:str,*,maximum:int=128)->tuple[PrivacyFinding,...]:
    if not isinstance(text,str) or len(text.encode())>500000:
        raise EvalError('invalid privacy scan text')
    findings=[]
    for rule,regex in _PATTERNS.items():
        for match in regex.finditer(text):
            findings.append(PrivacyFinding(rule,match.start(),match.end()))
            if len(findings)>maximum:raise EvalError('too many sensitive findings')
    return tuple(sorted(findings,key=lambda f:(f.start,f.category)))
