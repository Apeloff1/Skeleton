"""Thread-safe in-process reservation ledger with no implicit refund of effects.

Not authoritative global billing. Use the existing durable SQLite cost
accounting for cross-process and restart-safe resource custody.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from ..contracts import fail

@dataclass(frozen=True,slots=True)
class Reservation:
    tenant:str
    request_id:str
    prompt_reserved:int
    output_reserved:int
    cost_unit:str="tokens"

class Quota:
    def __init__(self,*,tenant_ceiling=65536,global_ceiling=262144,maximum=4096):
        if any(type(x) is not int for x in (tenant_ceiling,global_ceiling,maximum)):
            fail("integer quota policy required")
        if not 1<=tenant_ceiling<=global_ceiling<=100000000 or not 1<=maximum<=100000:
            fail("invalid quota resource ceiling")
        self._lock=RLock()
        self._tenant_max=tenant_ceiling
        self._global_max=global_ceiling
        self._maximum=maximum
        self._spent={}
        self._pending={}
        self._global_spent=0

    def reserve(self,tenant,request_id,*,prompt,output):
        if (type(tenant) is not str or not tenant or type(request_id) is not str
            or not request_id or len(tenant)>48 or len(request_id)>128):
            fail("invalid quota principal")
        if (type(prompt) is not int or type(output) is not int or
            prompt<0 or output<0 or not 1<=prompt+output<=100000000):
            fail("quota reservation must be exact bounded integers")
        key=(tenant,request_id)
        with self._lock:
            if key in self._pending or len(self._pending)>=self._maximum:
                fail("duplicate/full quota reservation")
            outstanding=sum(r.prompt_reserved+r.output_reserved for r in self._pending.values())
            tenant_outstanding=sum(r.prompt_reserved+r.output_reserved
                                   for r in self._pending.values() if r.tenant==tenant)
            if self._spent.get(tenant,0)+tenant_outstanding+prompt+output>self._tenant_max:
                fail("tenant quota reservation exhausted")
            if self._global_spent+outstanding+prompt+output>self._global_max:
                fail("global quota reservation exhausted")
            reservation=Reservation(tenant,request_id,prompt,output)
            self._pending[key]=reservation
            return reservation

    def commit(self,tenant,request_id,*,prompt,output):
        if (type(prompt) is not int or type(output) is not int
            or prompt<0 or output<0):fail("actual cost must be exact nonnegative")
        key=(tenant,request_id)
        with self._lock:
            old=self._pending.get(key)
            if old is None:fail("no live quota reservation")
            if prompt>old.prompt_reserved or output>old.output_reserved:
                fail("actual inference consumption exceeds reservation")
            cost=prompt+output
            self._spent[tenant]=self._spent.get(tenant,0)+cost
            self._global_spent+=cost
            del self._pending[key]
            return {"tenant":tenant,"request_id":request_id,
                    "charged_tokens":cost,"global_spent":self._global_spent}

    def release_without_effect(self,tenant,request_id,*,effect_absent):
        if effect_absent is not True:fail("uncertain side effects cannot be refunded")
        with self._lock:
            key=(tenant,request_id)
            if key not in self._pending:fail("unknown reservation")
            del self._pending[key]

    def snapshot(self):
        with self._lock:
            return {"global_spent":self._global_spent,
                "reserved":sum(r.prompt_reserved+r.output_reserved
                               for r in self._pending.values()),
                "pending_count":len(self._pending),
                "global_capacity":self._global_max}
