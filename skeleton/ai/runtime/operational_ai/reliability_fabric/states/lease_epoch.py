"""Thread-safe bounded lease_epoch evidence receipts. Not cross-process durability."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from ..engine import validate

class Evidence:
    def __init__(self,maximum=128):
        if type(maximum) is not int or not 1<=maximum<=4096:fail("invalid bounded evidence capacity")
        self._lock=RLock()
        self._max=maximum
        self._records={}
    def observe(self,key,record):
        if type(key) is not str or not key or len(key)>96:
            fail("invalid receipt identity")
        validated=validate("lease_epoch",record)
        with self._lock:
            if key in self._records:fail("duplicate evidence key")
            if len(self._records)>=self._max:fail("evidence memory ceiling reached")
            self._records[key]=validated
            return dict(validated)
    def read(self,key):
        with self._lock:
            record=self._records.get(key)
            return None if record is None else dict(record)
    def forget(self,key):
        with self._lock:
            if key not in self._records:fail("unknown evidence key")
            del self._records[key]
