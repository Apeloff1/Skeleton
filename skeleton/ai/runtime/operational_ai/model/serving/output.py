"""Safe rendering of backend output for clients and logs."""
from __future__ import annotations
import re
from .contracts import ServingError

_SECRET=re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/-]{12,}|(api[_-]?key\s*[:=]\s*)[^\s,;]+')


def safe_output(text:str,maximum:int=262144)->str:
    if not isinstance(text,str) or len(text.encode('utf8'))>maximum:
        raise ServingError('backend output exceeds byte ceiling')
    if any(ord(ch)<32 and ch not in '\n\r\t' for ch in text):
        raise ServingError('backend output contains control characters')
    return text


def redact_log(text:str)->str:
    return _SECRET.sub(lambda m:(m.group(1) or m.group(2))+'[REDACTED]',safe_output(text))
