"""Deterministic masking of obvious credentials in untrusted source context.

This is defense-in-depth and *not* a comprehensive DLP classifier; never
represent the absence of matches as proof a source contains no secrets.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from ..authority.canonical import ContractViolation,sha256

_PATTERNS=(
    ("private-key",re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]{0,32768}?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer-token",re.compile(r"\bBearer\s+[A-Za-z0-9_./+~=-]{16,}\b",re.IGNORECASE)),
    ("secret-assignment",re.compile(r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[\"']?[A-Za-z0-9_./+~=-]{12,}",re.IGNORECASE)),
)

@dataclass(frozen=True,slots=True)
class Redaction:
    text:str
    mask_count:int
    source_sha256:str
    rules:tuple[str,...]


def redact(source_text:str)->Redaction:
    if not isinstance(source_text,str) or len(source_text.encode("utf-8"))>262144:
        raise ContractViolation("invalid redaction source")
    rules=[]
    masked=source_text
    total=0
    for label,pattern in _PATTERNS:
        masked,count=pattern.subn(f"[REDACTED:{label}]",masked)
        if count:
            total+=count
            rules.append(label)
    return Redaction(masked,total,sha256(source_text.encode("utf-8")),tuple(rules))
