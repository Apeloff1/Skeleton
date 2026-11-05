"""Explicit local-only model backend selection with pinned epoch constraints."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail

class LocalRouter:
    def __init__(self,maximum=64):
        if type(maximum) is not int or not 1<=maximum<=512:
            fail("invalid local model inventory limit")
        self._maximum=maximum;self._lock=RLock()
        self._slots={}

    def register(self,name,*,model_sha,tokenizer_sha,concurrency=1,local=True):
        if type(name) is not str or not name or len(name)>96:
            fail("invalid backend name")
        if type(local) is not bool or not local: fail("hosted routing forbidden")
        if type(concurrency) is not int or not 1<=concurrency<=64:
            fail("invalid concurrency ceiling")
        import re
        if any(type(x) is not str or re.fullmatch("[0-9a-f]{64}",x) is None
               for x in (model_sha,tokenizer_sha)):
            fail("unattested model identity")
        with self._lock:
            if name in self._slots or len(self._slots)>=self._maximum:
                fail("duplicate or full backend inventory")
            self._slots[name]={"model_sha":model_sha,"tokenizer_sha":tokenizer_sha,
                               "max":concurrency,"active":0,"healthy":False}

    def observe(self,name,*,healthy):
        if type(healthy) is not bool: fail("health must be explicit boolean")
        with self._lock:
            if name not in self._slots: fail("unknown backend")
            self._slots[name]["healthy"]=healthy

    def admit(self,*,model_sha,tokenizer_sha):
        with self._lock:
            eligible=[(name,slot) for name,slot in self._slots.items()
                      if slot["model_sha"]==model_sha and
                         slot["tokenizer_sha"]==tokenizer_sha and
                         slot["healthy"] and slot["active"]<slot["max"]]
            if not eligible: fail("no healthy approved local model capacity")
            name,slot=min(eligible,key=lambda pair:(pair[1]["active"],pair[0]))
            slot["active"]+=1
            return name

    def release(self,name):
        with self._lock:
            if name not in self._slots or self._slots[name]["active"]<=0:
                fail("unknown or unadmitted backend release")
            self._slots[name]["active"]-=1

    def retire(self,name):
        with self._lock:
            if name not in self._slots or self._slots[name]["active"]:
                fail("cannot retire active model")
            del self._slots[name]
