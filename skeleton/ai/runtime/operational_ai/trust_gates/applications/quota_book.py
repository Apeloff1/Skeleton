"""Process-local budget reservations; not a substitute for durable cross-process billing."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from ..engine import validate

class QuotaBook:
    def __init__(self, *, tenant_ceiling, global_ceiling):
        if type(tenant_ceiling) is not int or type(global_ceiling) is not int:
            fail("integer quota limits required")
        if not 1<=tenant_ceiling<=global_ceiling<=100000000:
            fail("invalid quota policy")
        self.tenant_ceiling=tenant_ceiling
        self.global_ceiling=global_ceiling
        self._lock=RLock()
        self._used={}
        self._pending={}
        self._consumed=0

    def reserve(self, tenant, request_id, *, prompt_tokens, output_tokens):
        if type(prompt_tokens) is not int or type(output_tokens) is not int:
            fail("exact quota integer required")
        if prompt_tokens<0 or output_tokens<0 or prompt_tokens+output_tokens==0:
            fail("empty or negative reservation")
        with self._lock:
            key=(tenant,request_id)
            if key in self._pending: fail("duplicate reservation")
            used=self._used.get(tenant,0)
            outstanding=sum(p+o for t,p,o in self._pending.values() if t==tenant)
            total_pending=sum(p+o for t,p,o in self._pending.values())
            receipt=validate("quota",{
                "tenant":tenant,"prompt_used":used+outstanding,"output_used":0,
                "new_prompt":prompt_tokens,"new_output":output_tokens,
                "tenant_ceiling":self.tenant_ceiling,
                "global_remaining":self.global_ceiling-self._consumed-total_pending})
            self._pending[key]=(tenant,prompt_tokens,output_tokens)
            return receipt

    def release(self, tenant, request_id):
        with self._lock:
            key=(tenant,request_id)
            if key not in self._pending: fail("unknown quota reservation")
            self._pending.pop(key)

    def commit(self, tenant, request_id, *, actual_prompt, actual_output):
        with self._lock:
            key=(tenant,request_id)
            if key not in self._pending: fail("missing quota reservation")
            _,p,o=self._pending[key]
            if (type(actual_prompt) is not int or type(actual_output) is not int
                or not 0<=actual_prompt<=p or not 0<=actual_output<=o):
                fail("actual usage outside reserved bounds")
            spend=actual_prompt+actual_output
            self._used[tenant]=self._used.get(tenant,0)+spend
            self._consumed+=spend
            del self._pending[key]
            return {"tenant":tenant,"request_id":request_id,"charged_tokens":spend}
