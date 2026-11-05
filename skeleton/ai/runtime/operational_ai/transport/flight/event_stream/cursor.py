"""Replay cursor MAC binds principal, job, ordinal and exact event digest.

The private service bearer is used only as key input, never placed into a
cursor, response, event payload or log. Repeated calls are deterministic and
survive a service restart while the independently-provisioned bearer remains.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import hmac
import re
from .contracts import InvalidCursor,identifier,hexdigest,bounded

_CURSOR=re.compile(r'^v1\.([1-9][0-9]{0,3})\.([0-9a-f]{64})\.([0-9a-f]{64})$')

@dataclass(frozen=True,slots=True)
class StreamCursor:
    ordinal:int
    digest:str
    def __post_init__(self):
        bounded(self.ordinal,1,4096,'cursor ordinal')
        hexdigest(self.digest)

class CursorAuthority:
    def __init__(self,bearer:str,principal:str):
        if type(bearer) is not str or not 32<=len(bearer)<=512 or not bearer.isascii() or any(ord(x)<33 or ord(x)>126 for x in bearer):
            raise InvalidCursor('private bearer secret required')
        if type(principal) is not str or not 1<=len(principal)<=256 or '\0' in principal:
            raise InvalidCursor('private principal scope required')
        self._secret=sha256(b'skeleton.ai.flight-cursor.v1\0'+bearer.encode('ascii')).digest()
        self._principal=principal
    def _tag(self,job:str,ordinal:int,digest:str)->str:
        message=('v1\0'+self._principal+'\0'+job+'\0'+str(ordinal)+'\0'+digest).encode('utf8')
        return hmac.new(self._secret,message,sha256).hexdigest()
    def encode(self,job:str,ordinal:int,digest:str)->str:
        identifier(job)
        cursor=StreamCursor(ordinal,digest)
        return f'v1.{cursor.ordinal}.{cursor.digest}.{self._tag(job,cursor.ordinal,cursor.digest)}'
    def decode(self,job:str,value:str)->StreamCursor:
        identifier(job)
        if type(value)is not str or len(value)>160:
            raise InvalidCursor('stream cursor is malformed')
        match=_CURSOR.fullmatch(value)
        if match is None:
            raise InvalidCursor('stream cursor syntax invalid')
        ordinal,digest,provided=int(match.group(1)),match.group(2),match.group(3)
        try:cursor=StreamCursor(ordinal,digest)
        except ValueError as exc:raise InvalidCursor('stream cursor range invalid') from exc
        if not hmac.compare_digest(provided,self._tag(job,cursor.ordinal,cursor.digest)):
            raise InvalidCursor('stream cursor was not issued for this job and principal')
        return cursor
