"""Tenant-pinned model router; never implicit hosted fallback."""
from __future__ import annotations
from threading import Lock
from .contracts import ModelIdentity,ServingError,required_id

class PinnedRouter:
    def __init__(self):
        self._lock=Lock();self._routes:dict[str,ModelIdentity]={}

    def assign(self,tenant:str,identity:ModelIdentity)->None:
        required_id(tenant,'tenant')
        with self._lock:self._routes[tenant]=identity

    def route(self,tenant:str)->ModelIdentity:
        required_id(tenant,'tenant')
        with self._lock:
            if tenant not in self._routes:raise ServingError('tenant has no approved local model')
            return self._routes[tenant]

    def revoke(self,tenant:str)->None:
        with self._lock:self._routes.pop(tenant,None)
