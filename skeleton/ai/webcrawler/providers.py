"""Source-provider abstraction for authorized APIs, search systems and crawlers."""
from __future__ import annotations
from dataclasses import dataclass,replace
from typing import Iterable,Protocol,Mapping
from .core import canonicalize_url
@dataclass(frozen=True)
class SourceCandidate:
    url:str;title:str="";snippet:str="";provider:str="";score:float=0.0
    metadata:Mapping[str,object]|None=None
@dataclass(frozen=True)
class ProviderFailure:
    provider:str;error_type:str
class SourceProvider(Protocol):
    name:str
    def search(self,query:str,*,limit:int)->Iterable[SourceCandidate]: ...
class FederatedDiscovery:
    def __init__(self,providers:Iterable[SourceProvider]):
        self.providers=tuple(providers);self.last_failures:tuple[ProviderFailure,...]=()
    def discover(self,query:str,*,per_provider:int=20,total_limit:int=100)->list[SourceCandidate]:
        merged={};failures=[]
        for provider in self.providers:
            try:candidates=provider.search(query,limit=per_provider)
            except Exception as exc:
                failures.append(ProviderFailure(provider.name,type(exc).__name__));continue
            try:
                for raw in candidates:
                    try:url=canonicalize_url(raw.url)
                    except ValueError:continue
                    c=replace(raw,url=url,provider=provider.name)
                    old=merged.get(url)
                    if old is None or c.score>old.score:merged[url]=c
            except Exception as exc:
                failures.append(ProviderFailure(provider.name,type(exc).__name__))
        self.last_failures=tuple(failures)
        groups={}
        for c in merged.values():groups.setdefault(c.provider,[]).append(c)
        for values in groups.values():values.sort(key=lambda x:(-x.score,x.url))
        out=[];names=sorted(groups)
        while names and len(out)<total_limit:
            remaining=[]
            for name in names:
                if groups[name] and len(out)<total_limit:out.append(groups[name].pop(0))
                if groups[name]:remaining.append(name)
            names=remaining
        return out
