"""Independent chain of SHA-256 receipts for local output diagnostics.

This is a process-local checkable digest sequence, not durable conversation
commit authority; SQLite ExecutionSpine remains the owner of committed turns.
"""
from __future__ import annotations
import hashlib
from threading import RLock
from .contracts import canonical,identity_hash,identifier,refuse

class ReceiptAudit:
    def __init__(self,max_events=1024):
        if type(max_events) is not int or not 1<=max_events<=100000:
            refuse("invalid audit maximum")
        self._lock=RLock();self._max=max_events
        self._events=[];self._head="0"*64
    def append(self,operation,request_id,output_sha256):
        identifier(operation);identifier(request_id);identity_hash(output_sha256)
        with self._lock:
            if len(self._events)>=self._max:refuse("audit budget full")
            event={"sequence":len(self._events)+1,"operation":operation,
                   "request_id":request_id,"output_sha256":output_sha256,
                   "previous_sha256":self._head}
            event["sha256"]=hashlib.sha256(canonical(event)).hexdigest()
            self._events.append(event);self._head=event["sha256"]
            return dict(event)
    def verify(self):
        with self._lock:
            expected="0"*64
            for idx,event in enumerate(self._events,1):
                if event["sequence"]!=idx or event["previous_sha256"]!=expected:
                    refuse("local receipt chain sequence or parent fork")
                raw={k:v for k,v in event.items() if k!="sha256"}
                if hashlib.sha256(canonical(raw)).hexdigest()!=event["sha256"]:
                    refuse("local receipt content tampered")
                expected=event["sha256"]
            return {"count":len(self._events),"head_sha256":expected}
