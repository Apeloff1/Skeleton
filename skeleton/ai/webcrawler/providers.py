"""Source-provider abstraction for authorized APIs, search systems and crawlers."""
from __future__ import annotations
from dataclasses import dataclass,replace
import math
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
        names=[getattr(p,"name",None) for p in self.providers]
        if any(not isinstance(x,str) or not x.strip() for x in names):raise ValueError("provider names must be non-empty")
        if len(set(names))!=len(names):raise ValueError("provider names must be unique")
    def discover_temporal(self,query:str,*,target_decades:Iterable[int]=(),per_provider:int=20,total_limit:int=100)->list[SourceCandidate]:
        decades=tuple(sorted({int(d) for d in target_decades}))
        if any(d%10 for d in decades):raise ValueError("target decades must be decade starts")
        base=self.discover(query,per_provider=per_provider,total_limit=max(total_limit,total_limit*2))
        if not decades:return base[:total_limit]
        def temporal_score(candidate):
            text=(candidate.url+" "+candidate.title+" "+candidate.snippet).lower()
            hits=sum(1 for d in decades if any(str(y) in text for y in range(d,d+10)) or f"{d}s" in text)
            return (hits,candidate.score)
        return sorted(base,key=lambda x:(-temporal_score(x)[0],-temporal_score(x)[1],x.url))[:total_limit]
    def discover(self,query:str,*,per_provider:int=20,total_limit:int=100)->list[SourceCandidate]:
        if not isinstance(query,str) or not query.strip():raise ValueError("query is required")
        if isinstance(per_provider,bool) or not isinstance(per_provider,int) or per_provider<1:raise ValueError("per_provider must be positive")
        if isinstance(total_limit,bool) or not isinstance(total_limit,int) or total_limit<1:raise ValueError("total_limit must be positive")
        merged={};failures=[]
        for provider in self.providers:
            try:candidates=provider.search(query,limit=per_provider)
            except Exception as exc:
                failures.append(ProviderFailure(provider.name,type(exc).__name__));continue
            try:
                for raw in candidates:
                    try:url=canonicalize_url(raw.url)
                    except ValueError:continue
                    if not isinstance(raw.score,(int,float)) or isinstance(raw.score,bool) or not math.isfinite(raw.score):continue
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
