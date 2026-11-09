"""Readable process-independent SSE facade over canonical flight transitions."""
from __future__ import annotations
from .cursor import CursorAuthority
from .reader import EventReader
from .poller import read_until
from .query import StreamQuery
from .render import encode
from .contracts import StreamError,StreamPolicy

class EventStream:
    def __init__(self,ledger,bearer:str,*,policy:StreamPolicy|None=None):
        self.policy=policy or StreamPolicy()
        principal=ledger.identity.key()
        self.reader=EventReader(ledger,CursorAuthority(bearer,principal))
    def read(self,query:StreamQuery)->tuple[bytes,dict]:
        if not isinstance(query,StreamQuery):raise StreamError('validated query required')
        if query.limit>self.policy.max_events or query.wait_ms>self.policy.max_wait_ms:
            raise StreamError('event stream exceeds server capacity policy')
        snapshot=read_until(self.reader,query.job_id,query.cursor,
                limit=query.limit,wait_ms=query.wait_ms)
        raw=encode(snapshot,limit_bytes=self.policy.max_payload_bytes)
        return raw,snapshot.record()
