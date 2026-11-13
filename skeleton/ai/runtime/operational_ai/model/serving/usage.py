"""Integer-only consumption accounting for local model serving."""
from __future__ import annotations
from threading import Lock
from .contracts import ServingError,required_id

class UsageLedger:
    def __init__(self,max_entries:int=2048):
        if type(max_entries) is not int or max_entries<=0:raise ServingError('invalid usage capacity')
        self._lock=Lock();self._map={};self._cap=max_entries

    def charge(self,tenant:str,prompt_tokens:int,generated_tokens:int)->None:
        required_id(tenant,'tenant')
        if any(type(x) is not int or not 0<=x<=10**8 for x in (prompt_tokens,generated_tokens)):
            raise ServingError('invalid token use')
        with self._lock:
            if tenant not in self._map and len(self._map)>=self._cap:
                raise ServingError('usage accounting cardinality exceeded')
            p,g=self._map.get(tenant,(0,0))
            self._map[tenant]=(p+prompt_tokens,g+generated_tokens)

    def get(self,tenant:str)->tuple[int,int]:
        required_id(tenant,'tenant')
        with self._lock:return self._map.get(tenant,(0,0))
