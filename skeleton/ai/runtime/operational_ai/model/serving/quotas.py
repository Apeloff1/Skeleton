"""Tenant token quotas with bounded in-memory reservations."""
from __future__ import annotations
from threading import RLock
from .contracts import ServingError,required_id

class TenantQuotas:
    def __init__(self,per_tenant_tokens:int=65536,max_tenants:int=1024):
        if type(per_tenant_tokens) is not int or per_tenant_tokens<=0 or type(max_tenants) is not int or max_tenants<1:
            raise ServingError('invalid tenant quota ceiling')
        self.capacity=per_tenant_tokens
        self.max_tenants=max_tenants
        self._balances:dict[str,int]={}
        self._lock=RLock()

    def reserve(self,tenant:str,estimated_tokens:int)->None:
        required_id(tenant,'tenant')
        if type(estimated_tokens) is not int or not 0<estimated_tokens<=self.capacity:
            raise ServingError('invalid token reservation')
        with self._lock:
            if tenant not in self._balances and len(self._balances)>=self.max_tenants:
                raise ServingError('tenant cardinality limit exceeded')
            left=self._balances.get(tenant,self.capacity)
            if left<estimated_tokens:raise ServingError('tenant quota exceeded')
            self._balances[tenant]=left-estimated_tokens

    def refund(self,tenant:str,unused_tokens:int)->None:
        required_id(tenant,'tenant')
        if type(unused_tokens) is not int or unused_tokens<0:
            raise ServingError('invalid quota refund')
        with self._lock:
            if tenant not in self._balances:raise ServingError('tenant not reserved')
            self._balances[tenant]=min(self.capacity,self._balances[tenant]+unused_tokens)

    def remaining(self,tenant:str)->int:
        required_id(tenant,'tenant')
        with self._lock:return self._balances.get(tenant,self.capacity)
