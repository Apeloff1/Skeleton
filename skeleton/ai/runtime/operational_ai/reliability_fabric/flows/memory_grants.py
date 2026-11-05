"""Strong-key, one-shot tenant/source memory authority with existing HMAC custody."""
from __future__ import annotations
from ..contracts import fail
from skeleton.ai.runtime.operational_ai.trust_gates.control.consent import ConsentAuthority

class MemoryGrants:
    def __init__(self,key,*,maximum_consumed=100000):
        self._authority=ConsentAuthority(key,maximum_consumed=maximum_consumed)

    def issue(self,*,tenant,source_id,operator,now,expires,approved):
        if approved is not True:fail("memory grant needs independently provided consent")
        return self._authority.issue(tenant=tenant,source_id=source_id,
              operator=operator,now=now,expires=expires,approved=True)

    def consume(self,grant,*,tenant,source_id,now):
        proof=self._authority.verify(grant,tenant=tenant,source_id=source_id,
                                      now=now,consume=True)
        if proof["tenant"]!=tenant or proof["source_id"]!=source_id:
            fail("cross-tenant HMAC memory grant")
        return {"consented":True,"tenant":tenant,"source_id":source_id,
                "persisted":False,"release_certified":False}
