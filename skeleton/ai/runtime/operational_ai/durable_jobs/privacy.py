"""Conservative credential suppression for diagnostic logging.

No PII/DLP completeness assertion; never log raw prompts by default.
"""
from __future__ import annotations
import re
from .canonical import require_text

_PATTERNS=(
    re.compile(r"(?i)\bBearer[ \t]+[a-z0-9._~+/-]{12,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret)[ \t]*[:=][ \t]*[a-z0-9._~/-]{10,}"),
)
TOKEN="[REDACTED]"


def redact(text:str)->str:
    value=require_text(text,32768,"log-message",allow_empty=True)
    for pattern in _PATTERNS:
        value=pattern.sub(TOKEN,value)
    return value


def safe_job_summary(view:dict)->dict:
    if type(view) is not dict:
        from .errors import deny
        deny("privacy-view")
    keys=("job_id","request_id","state","attempt","priority","created_ms",
          "updated_ms","failure_code")
    return {k:view.get(k) for k in keys if k in view}
