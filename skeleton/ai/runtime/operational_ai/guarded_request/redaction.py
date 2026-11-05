"""Narrow pre-model redaction for common credential-bearing envelopes.

This control intentionally does not claim complete PII/DLP coverage.
"""
from __future__ import annotations

import re

from .contracts import require_text

_PATTERNS = (
    re.compile(r"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token)[ \t]*[:=][ \t]*[A-Za-z0-9._~-]{10,}"),
)
_REDACTED = "[REDACTED_CREDENTIAL]"


def redact_credential_envelopes(text: str) -> tuple[str, int]:
    result = require_text(text, maximum=32768, field="untrusted-source")
    total = 0
    for pattern in _PATTERNS:
        result, count = pattern.subn(_REDACTED, result)
        total += count
    return result, total
