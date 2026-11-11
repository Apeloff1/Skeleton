"""Readable process-independent SSE facade over canonical flight transitions."""
from __future__ import annotations
from .cursor import CursorAuthority
from .reader import EventReader
from .poller import read_until
from .query import StreamQuery
from .render import encode
from .contracts import StreamError,StreamPolicy,identifier,bounded

class EventStream:
    def __init__(self,ledger,bearer:str,*,policy:StreamPolicy|None=None):
        self.policy=policy or StreamPolicy()
        principal=ledger.identity.key()
        self.reader=EventReader(ledger,CursorAuthority(bearer,principal))
    def read(self,query:StreamQuery)->tuple[bytes,dict]:
        if type(query) is not StreamQuery:
            raise StreamError('validated query required')
        identifier(query.job_id)
        bounded(query.limit,1,self.policy.max_events,'event batch')
        bounded(query.wait_ms,0,self.policy.max_wait_ms,'long poll')
        if query.cursor is not None and (type(query.cursor) is not str or not query.cursor):
            raise StreamError('invalid replay cursor')
        snapshot=read_until(self.reader,query.job_id,query.cursor,
                limit=query.limit,wait_ms=query.wait_ms)
        raw=encode(snapshot,limit_bytes=self.policy.max_payload_bytes)
        return raw,snapshot.record()
