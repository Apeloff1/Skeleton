"""Descriptor-anchored, no-clobber local publisher with crash-durable receipts.

Publishing a file and updating SQLite are different transactions. We publish
one immutable event by exclusive create, fsync it and its directory, then
ack the SQLite row. On crash, repeat checks EXACT bytes rather than rewriting
or creating a duplicate external side effect.
"""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
import os,stat
from hashlib import sha256
from .contracts import DeliveryHeld,DeliveryPolicy
from .projection import encode
from . import owner
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import open_private_root

class PrivateEventSink:
    def __init__(self,root:Path|str,*,policy:DeliveryPolicy|None=None):
        self.policy=policy or DeliveryPolicy()
        self._fd=open_private_root(root)
        self._closed=False
        self._identity=None
    def _require_open(self):
        if self._closed:raise DeliveryHeld('delivery spool is closed')
    def bind(self, identity):
        self._require_open()
        proof=owner.bind(self._fd,identity)
        self._identity=identity
        return proof

    def _lock_guard(self):
        return owner.guard(self._fd)

    def _require_bound(self):
        self._require_open()
        if self._identity is None:
            raise DeliveryHeld('delivery publisher is not owner-bound')
        owner.require(self._fd,self._identity)

    @staticmethod
    def _check(fd:int,expected_size:int|None=None)->int:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
            info.st_mode&0o077 or info.st_uid!=os.getuid()):
            raise DeliveryHeld('delivery file is unsafe or aliased')
        if not 1<=info.st_size<=524288 or (expected_size is not None and info.st_size!=expected_size):
            raise DeliveryHeld('delivery file is empty, truncated or oversized')
        return info.st_size
    def _read(self,name:str)->bytes:
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_NONBLOCK',0)|
                   getattr(os,'O_CLOEXEC',0),dir_fd=self._fd)
        try:
            size=self._check(fd)
            raw=os.read(fd,size+1)
            if len(raw)!=size:raise DeliveryHeld('delivery event changed while reading')
            self._check(fd,size)
            return raw
        finally:os.close(fd)
    def append(self,event:dict)->dict:
        self._require_bound()
        with owner.guard(self._fd):
            return self._append_locked(event)

    def _append_locked(self,event:dict)->dict:
        self._require_bound()
        filename,raw,sha=encode(event)
        if len(raw)>self.policy.max_receipt_bytes:
            raise DeliveryHeld('delivery event exceeds operator receipt limit')
        try:
            fd=os.open(filename,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|
                       getattr(os,'O_CLOEXEC',0),0o600,dir_fd=self._fd)
        except FileExistsError:
            if self._read(filename)!=raw:
                raise DeliveryHeld('existing delivery receipt is partial or conflicting')
            return {'event_key':event['event_key'],'delivery_sha256':sha,
                    'replayed':True,'bytes':len(raw)}
        try:
            offset=0
            while offset<len(raw):
                n=os.write(fd,raw[offset:])
                if n<=0:raise DeliveryHeld('durable delivery write incomplete')
                offset+=n
            self._check(fd,len(raw))
            os.fsync(fd)
            os.fsync(self._fd)
        finally:os.close(fd)
        return {'event_key':event['event_key'],'delivery_sha256':sha,
                'replayed':False,'bytes':len(raw)}
    def verify(self,event:dict)->dict:
        self._require_bound()
        with owner.guard(self._fd):
            return self._verify_locked(event)

    def _verify_locked(self,event:dict)->dict:
        self._require_bound()
        filename,raw,sha=encode(event)
        if self._read(filename)!=raw:
            raise DeliveryHeld('saved delivery bytes conflict with authoritative event')
        return {'event_key':event['event_key'],'delivery_sha256':sha,'verified':True}
    def inventory(self)->dict:
        self._require_bound()
        with owner.guard(self._fd):
            return self._inventory_locked()

    def _inventory_locked(self)->dict:
        self._require_bound()
        names=os.listdir(self._fd)
        if len(names)>self.policy.max_inventory:
            raise DeliveryHeld('bounded delivery inventory exceeded')
        count=0
        for name in names:
            if name in (owner.LOCK,owner.OWNER):continue
            if not name.endswith('.event') or len(name)!=70 or any(x not in '0123456789abcdef' for x in name[:-6]):
                raise DeliveryHeld('unrecognized file in private delivery spool')
            from .verify import verify_saved_receipt
            verify_saved_receipt(self._read(name),name)
            count+=1
        return {'status':'verified-private-delivery-inventory','files':count,
                'model_calls':0,'unbounded_replay':False}
    def close(self):
        if not self._closed:
            self._closed=True;os.close(self._fd)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
