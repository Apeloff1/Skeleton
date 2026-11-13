"""Bounded in-process citation_provenance evidence ledger, not durable release authority."""
from __future__ import annotations
from threading import RLock
from . import __package__ as _unused
from ..contracts import fail
from ..engine import validate

class Evidence:
    def __init__(self,maximum=128):
        if type(maximum) is not int or not 1<=maximum<=4096:fail("invalid evidence ceiling")
        self._lock=RLock()
        self._ceiling=maximum
        self._rows={}
    def observe(self,key,record):
        if type(key) is not str or not key or len(key)>96:
            fail("invalid source evidence key")
        receipt=validate("citation_provenance",record)
        with self._lock:
            if key in self._rows:fail("duplicate evidence identity")
            if len(self._rows)>=self._ceiling:fail("bounded evidence ledger full")
            self._rows[key]=receipt
            return dict(receipt)
    def read(self,key):
        with self._lock:
            item=self._rows.get(key)
            return None if item is None else dict(item)
    def forget(self,key):
        with self._lock:
            if key not in self._rows:fail("unknown evidence tombstone")
            del self._rows[key]
