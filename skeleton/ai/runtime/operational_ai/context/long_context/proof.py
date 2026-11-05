"""Source validation of every admitted passage against immutable digest."""
from __future__ import annotations
import hmac
from hashlib import sha256
from .contracts import Span,ContextError


def verify_source(span:Span,original:bytes,*,start:int=0,end:int|None=None)->bool:
    if end is None:end=len(original)
    if not 0<=start<=end<=len(original):raise ContextError('invalid source byte offsets')
    try:content=original[start:end].decode('utf8')
    except UnicodeDecodeError:return False
    return hmac.compare_digest(sha256(content.encode()).hexdigest(),span.digest)
