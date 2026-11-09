"""Process-local idempotency arbitration before authoritative SQLite commit.

This ephemeral table cannot replace durable request replay in OfflineChatStore.
"""
from __future__ import annotations
from threading import RLock
from ..contracts import fail

class RequestDedupe:
    def __init__(self, maximum=10000):
        if type(maximum) is not int or not 1<=maximum<=100000:
            fail("invalid idempotency table bound")
        self._cap=maximum
        self._lock=RLock()
        self._records={}

    def begin(self,tenant,request_id,signature):
        key=(tenant,request_id)
        if any(type(x) is not str or not x or len(x)>128 for x in (*key,signature)):
            fail("invalid request identity")
        with self._lock:
            old=self._records.get(key)
            if old is not None:
                if old["signature"]!=signature: fail("conflicting idempotency key")
                if old["state"]=="pending": fail("concurrent duplicate in progress")
                return ("replay",old["receipt"])
            if len(self._records)>=self._cap: fail("idempotency table full")
            self._records[key]={"signature":signature,"state":"pending","receipt":None}
            return ("new",None)

    def commit(self,tenant,request_id,signature,receipt):
        key=(tenant,request_id)
        if type(receipt) is not dict or not receipt:
            fail("durable receipt required before idempotency commit")
        with self._lock:
            old=self._records.get(key)
            if old is None or old["signature"]!=signature:
                fail("idempotency lease missing or conflicted")
            if old["state"]=="committed":
                if old["receipt"]!=receipt: fail("double commit divergence")
                return dict(old["receipt"])
            old["state"]="committed";old["receipt"]=dict(receipt)
            return dict(receipt)

    def abort(self,tenant,request_id,signature):
        key=(tenant,request_id)
        with self._lock:
            old=self._records.get(key)
            if old is None or old["signature"]!=signature or old["state"]!="pending":
                fail("only pending original request may abort")
            del self._records[key]

    def get(self,tenant,request_id):
        with self._lock:
            value=self._records.get((tenant,request_id))
            return None if value is None else {"state":value["state"],
                     "signature":value["signature"],
                     "receipt":None if value["receipt"] is None else dict(value["receipt"])}
