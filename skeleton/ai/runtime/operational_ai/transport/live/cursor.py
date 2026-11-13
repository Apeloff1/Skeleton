"""Signed, scope-bound event cursors with expiry and tamper resistance."""
from __future__ import annotations
from dataclasses import dataclass
import base64,hashlib,hmac,json,time,re

class CursorError(ValueError):pass
_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')

@dataclass(frozen=True,slots=True)
class EventCursor:
    session:str
    tenant:str
    user:str
    seq:int
    head_sha:str
    expires_ns:int
    def __post_init__(self):
        if any(not _ID.fullmatch(x) for x in (self.session,self.tenant,self.user)):
            raise CursorError('invalid cursor scope')
        if type(self.seq) is not int or not 0<=self.seq<=2**53-1:
            raise CursorError('cursor sequence invalid')
        if not re.fullmatch(r'[0-9a-f]{64}',self.head_sha):
            raise CursorError('cursor journal identity invalid')
        if type(self.expires_ns) is not int or self.expires_ns<=0:
            raise CursorError('cursor expiry invalid')

class CursorSigner:
    def __init__(self,key:bytes):
        if not isinstance(key,bytes) or len(key)<32:
            raise CursorError('cursor signing requires 256-bit key')
        self._key=key

    def issue(self,cursor:EventCursor)->str:
        raw=json.dumps([cursor.session,cursor.tenant,cursor.user,cursor.seq,cursor.head_sha,cursor.expires_ns],separators=(',',':')).encode()
        mac=hmac.new(self._key,raw,hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac+raw).rstrip(b'=').decode('ascii')

    def verify(self,token:str,*,session:str,tenant:str,user:str,
               now_ns:int|None=None)->EventCursor:
        if not isinstance(token,str) or len(token)>1024 or not re.fullmatch(r'[A-Za-z0-9_-]+',token):
            raise CursorError('invalid cursor syntax')
        try:
            blob=base64.urlsafe_b64decode(token+'='*((-len(token))%4))
            mac,raw=blob[:32],blob[32:]
            if len(mac)!=32 or not hmac.compare_digest(mac,hmac.new(self._key,raw,hashlib.sha256).digest()):
                raise CursorError('cursor authentication failed')
            fields=json.loads(raw)
            if not isinstance(fields,list) or len(fields)!=6:
                raise CursorError('invalid cursor record')
            cursor=EventCursor(*fields)
        except (ValueError,UnicodeError,TypeError) as exc:
            raise CursorError('cursor malformed') from exc
        if (cursor.session,cursor.tenant,cursor.user)!=(session,tenant,user):
            raise CursorError('cross-scope cursor reuse denied')
        now=time.time_ns() if now_ns is None else now_ns
        if cursor.expires_ns<=now:raise CursorError('expired cursor')
        return cursor
