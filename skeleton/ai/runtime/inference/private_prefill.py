"""Request-scoped private native CPU prefix retention.

This is disposable CPU KV state, never a conversation store, token authority,
persistent archive, or cross-tenant semantic cache. Only a trusted local host
registers an owner/scope. Prepared tokens and canonical runtime admission
remain authoritative. A lease detaches state before use; invalidation fences
in-flight publication. Generation creates no network or disk dependency.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import threading
import time

from skeleton.ai.model_runtime.native_llm_runtime import NativeConversationSession, NativeLLMRuntime
from skeleton.cortex.transformer import KVCache


def _scope(owner,session):
    return hashlib.sha256(json.dumps(
        {"cache_scope":session,"tenant_scope":owner},
        sort_keys=True,separators=(",",":"),ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


@dataclass(eq=False)
class _Entry:
    owner:str
    session:str
    expires:float
    epoch:object
    profile:str|None=None
    cache:KVCache|None=None
    size:int=0


@dataclass(frozen=True,slots=True)
class PrefixLease:
    key:str
    epoch:object
    cache:KVCache
    reused_tokens:int
    profile:str


class PrivatePrefillPool:
    def __init__(self,runtime:NativeLLMRuntime,*,max_bytes:int=8*1024**2,
                 max_scopes:int=8,ttl_seconds:int=120):
        if not isinstance(runtime,NativeLLMRuntime):
            raise TypeError("canonical native runtime required")
        for value,lo,hi in ((max_bytes,0,64*1024**2),(max_scopes,1,32),(ttl_seconds,1,600)):
            if type(value) is not int or not lo<=value<=hi:
                raise ValueError("invalid private prefix retention budget")
        self.runtime=runtime
        self.capacity=min(max_bytes,runtime.limits.max_kv_bytes//4)
        self.max_scopes=max_scopes
        self.ttl_seconds=ttl_seconds
        self._entries=OrderedDict()
        self._lock=threading.RLock()
        self._reused=0
        self._leases=0
        self._published=0
        self._evictions=0

    def _enabled(self):
        r=self.runtime
        return (type(r) is NativeLLMRuntime and self.capacity>0 and r.device.actual=="cpu" and not r.device.resident
                and r.model._accel is None and not r.model.use_mod)

    def _drop(self,key):
        entry=self._entries.pop(key,None)
        if entry is not None:
            self.runtime._release_idle_cpu_prefix(entry)
            if entry.cache is not None:
                self._evictions+=1

    def _expire(self,now):
        for key,entry in tuple(self._entries.items()):
            if entry.expires<=now:
                self._drop(key)

    def register(self,owner:str,session:str)->str:
        # owner is an opaque trusted host namespace (not an HTTP parameter).
        for value in (owner,session):
            if type(value) is not str or not 1<=len(value)<=512:
                raise ValueError("invalid private prefix host namespace")
        key=_scope(owner,session)
        now=time.monotonic()
        with self._lock:
            self._expire(now)
            if not self._enabled():
                self._drop(key)
                return key
            entry=self._entries.get(key)
            if entry is None:
                while len(self._entries)>=self.max_scopes:
                    self._drop(next(iter(self._entries)))
                entry=_Entry(owner,session,now+self.ttl_seconds,object())
                self._entries[key]=entry
            elif (entry.owner,entry.session)!=(owner,session):
                raise ValueError("private prefix scope identity collision")
            entry.expires=now+self.ttl_seconds
            self._entries.move_to_end(key)
        return key

    def forget(self,owner:str,session:str|None=None):
        with self._lock:
            for key,entry in tuple(self._entries.items()):
                if entry.owner==owner and (session is None or entry.session==session):
                    self._drop(key)

    def _compatible(self,cache,profile,entry):
        r=self.runtime
        model=r.model
        return (entry.profile==profile and type(cache) is KVCache
                and cache.owner is model and cache.n_layers==model.n_layers
                and cache.ctx==r.limits.max_context
                and cache.revision==(model.steps,model.fitted,model.tied,model.device,model.resident)
                and cache.next_position==len(cache.tokens)
                and all(len(bank)==cache.n_layers for bank in (cache.K,cache.V))
                and all(len(layer)==len(cache.tokens) for bank in (cache.K,cache.V) for layer in bank))

    def checkout(self,key,profile,prompt_ids)->PrefixLease|None:
        if key is None:
            return None
        with self._lock:
            self._expire(time.monotonic())
            if not self._enabled():
                self._drop(key)
                return None
            entry=self._entries.get(key)
            if entry is None:
                return None
            cache=entry.cache
            valid=self._compatible(cache,profile,entry) if cache is not None else False
            # Transfer exclusive ownership to the generation. No other
            # checkout can touch the detached bank or publish its old epoch.
            self.runtime._release_idle_cpu_prefix(entry)
            entry.size=0
            entry.cache=None
            entry.epoch=object()
            entry.profile=profile
            self._entries.move_to_end(key)
            self._leases+=1
            reused=0
            if valid:
                for token,other in zip(cache.tokens,prompt_ids):
                    if token!=other:
                        break
                    reused+=1
                # A truncated cache has no logits for its new last position.
                # Keep at least one fresh token in the new prompt if needed.
                if reused<len(cache.tokens) and reused==len(prompt_ids):
                    reused=max(0,reused-1)
                if reused and reused<len(cache.tokens):
                    for bank in (cache.K,cache.V):
                        for layer in bank:
                            del layer[reused:]
                    del cache.tokens[reused:]
                    cache.next_position=reused
                    cache.last_logits=None
                    cache.reserved_bytes=0
                if reused==len(prompt_ids) and cache.last_logits is None:
                    reused=0
            if not reused:
                cache=KVCache(self.runtime.model.n_layers,self.runtime.limits.max_context)
            self._reused+=reused
            return PrefixLease(key,entry.epoch,cache,reused,profile)

    def publish(self,lease:PrefixLease,full_ids:tuple[int,...],profile:str)->bool:
        """Admit only complete non-sliding, exact prefix state after success."""
        cache=lease.cache
        if (not self._enabled() or len(full_ids)>self.runtime.limits.max_context
                or not cache.tokens or tuple(cache.tokens)!=full_ids[:len(cache.tokens)]):
            return False
        with self._lock:
            self._expire(time.monotonic())
            entry=self._entries.get(lease.key)
            if (entry is None or entry.cache is not None or entry.epoch is not lease.epoch or profile!=lease.profile
                    or not self._compatible(cache,profile,entry)):
                return False
            if not NativeConversationSession._compact_retained_prefix(
                    cache,width=self.runtime.model.dim,budget=self.capacity):
                return False
            size=NativeConversationSession._retained_prefix_size(cache)
            if size>self.capacity:
                return False
            while sum(e.size for e in self._entries.values())+size>self.capacity:
                victims=[key for key,item in self._entries.items()
                         if key!=lease.key and item.cache is not None]
                if not victims:
                    return False
                self._drop(victims[0])
            if not self.runtime._reserve_idle_cpu_prefix(entry,size):
                return False
            entry.cache=cache
            entry.size=size
            entry.expires=time.monotonic()+self.ttl_seconds
            self._published+=1
            self._entries.move_to_end(lease.key)
            return True

    def stats(self):
        with self._lock:
            self._expire(time.monotonic())
            return {"capacity_bytes":self.capacity,
                    "retained_estimated_python_bytes":sum(e.size for e in self._entries.values()),
                    "registered_scopes":len(self._entries),
                    "retained_scopes":sum(e.cache is not None for e in self._entries.values()),
                    "checkout_count":self._leases,"published_count":self._published,
                    "reused_prefix_tokens":self._reused,"evictions":self._evictions}
