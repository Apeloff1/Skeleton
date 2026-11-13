"""Deterministic local SHA256 content chain; durable state is still SQLite-owned."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from ..contracts import canonical,fail

@dataclass(frozen=True,slots=True)
class ChainHead:
    sequence:int
    digest:str

class EventChain:
    def __init__(self,*,stream,maximum=65536):
        if type(stream) is not str or not stream or len(stream)>128:
            fail("invalid audit stream")
        if type(maximum) is not int or not 1<=maximum<=100000:
            fail("unbounded audit chain")
        self._stream=stream
        self._max=maximum
        self._events=[]
        self._lock=RLock()
        self._head="0"*64

    def append(self,kind,payload):
        if type(kind) is not str or not kind or len(kind)>96:
            fail("unknown event kind")
        body=canonical(payload,maximum=262144)
        with self._lock:
            if len(self._events)>=self._max:fail("event chain full")
            entry={"schema":"ai-event-chain.v1","stream":self._stream,
                "sequence":len(self._events)+1,"kind":kind,
                "payload_sha256":sha256(body).hexdigest(),
                "previous_sha256":self._head}
            record_digest=sha256(canonical(entry)).hexdigest()
            event={**entry,"sha256":record_digest}
            self._events.append(event)
            self._head=record_digest
            return dict(event)

    def verify(self):
        with self._lock:
            previous="0"*64
            for index,event in enumerate(self._events,1):
                if event["sequence"]!=index or event["previous_sha256"]!=previous:
                    fail("event chain sequence/parent inconsistency")
                raw={key:value for key,value in event.items() if key!="sha256"}
                if sha256(canonical(raw)).hexdigest()!=event["sha256"]:
                    fail("event chain content hash mismatch")
                previous=event["sha256"]
            return ChainHead(len(self._events),previous)

    def checkpoint(self):
        return self.verify()
