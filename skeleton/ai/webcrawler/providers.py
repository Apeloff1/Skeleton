"""Source-provider abstraction for authorized APIs, search systems and crawlers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable,Protocol,Mapping
from .core import CrawlDocument

@dataclass(frozen=True)
class SourceCandidate:
    url:str;title:str="";snippet:str="";provider:str="";score:float=0.0
    metadata:Mapping[str,object]|None=None

class SourceProvider(Protocol):
    name:str
    def search(self,query:str,*,limit:int)->Iterable[SourceCandidate]: ...

class FederatedDiscovery:
    def __init__(self,providers:Iterable[SourceProvider]):
        self.providers=tuple(providers)
    def discover(self,query:str,*,per_provider:int=20,total_limit:int=100)->list[SourceCandidate]:
        merged={}
        for provider in self.providers:
            for c in provider.search(query,limit=per_provider):
                old=merged.get(c.url)
                if old is None or c.score>old.score:merged[c.url]=c
        # diversity-aware round-robin by provider after provider-local ranking
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
