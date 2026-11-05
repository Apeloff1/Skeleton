"""In-memory append-only SHA chain with replayable exact-byte evidence."""
from __future__ import annotations
from threading import RLock
from .contracts import identifier,canonical,hash_bytes,fingerprint,refuse
class Audit:
    def __init__(self,stream_id,*,max_events=100000):
        identifier(stream_id)
        if type(max_events) is not int or not 1<=max_events<=1000000:
            refuse("audit event ceiling")
        self.id=stream_id;self.limit=max_events;self.lock=RLock();self.rows=[]
    def record(self,kind,evidence):
        identifier(kind)
        raw=canonical(evidence)
        with self.lock:
            if len(self.rows)>=self.limit:refuse("audit capacity reached")
            index=len(self.rows)+1
            prior="0"*64 if not self.rows else self.rows[-1][0]["event_sha256"]
            event={"schema":"offline-cognitive-audit.v1","stream_id":self.id,
                "index":index,"kind":kind,"payload_sha256":hash_bytes(raw),
                "previous_sha256":prior}
            event["event_sha256"]=fingerprint(event)
            self.rows.append((event,raw))
            return dict(event)
    def verify(self):
        with self.lock:
            previous="0"*64
            for index,(event,raw) in enumerate(self.rows,1):
                if index!=event["index"] or event["previous_sha256"]!=previous:
                    refuse("audit chain fork or missing event")
                if hash_bytes(raw)!=event["payload_sha256"]:
                    refuse("event payload modified")
                claim={k:v for k,v in event.items() if k!="event_sha256"}
                if fingerprint(claim)!=event["event_sha256"]:
                    refuse("event envelope hash mismatch")
                previous=event["event_sha256"]
            return {"count":len(self.rows),"head_sha256":previous,
                    "external_signature_proved":False}
    def snapshot(self):
        with self.lock:return tuple(dict(row) for row,_ in self.rows)
