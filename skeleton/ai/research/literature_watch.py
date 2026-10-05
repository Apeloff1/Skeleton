"""Deterministic literature-watch and triage contracts for VOL-211."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Iterable

class LiteratureWatchError(ValueError): pass
_KINDS=frozenset({"journal","conference","preprint","standard","repository","dataset"})
_PRIORITIES=frozenset({"low","normal","high","critical"})

def _token(name:str,value:object)->str:
    if not isinstance(value,str) or not value or value!=value.strip() or len(value)>1024: raise LiteratureWatchError(f"{name} must be non-empty normalized text")
    return value
def _sha(name:str,value:object)->str:
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value): raise LiteratureWatchError(f"{name} must be lowercase sha256")
    return value
def _digest(v:object)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class LiteratureSource:
    source_id:str; kind:str; trust_tier:int; adapter_id:str
    def __post_init__(self):
        object.__setattr__(self,"source_id",_token("source_id",self.source_id))
        kind=_token("kind",self.kind)
        if kind not in _KINDS: raise LiteratureWatchError("unknown literature source kind")
        object.__setattr__(self,"kind",kind)
        if isinstance(self.trust_tier,bool) or not isinstance(self.trust_tier,int) or not 0<=self.trust_tier<=3: raise LiteratureWatchError("trust_tier must be within [0,3]")
        object.__setattr__(self,"adapter_id",_token("adapter_id",self.adapter_id))

@dataclass(frozen=True,slots=True)
class LiteratureRecord:
    record_id:str; source_id:str; title:str; canonical_ref:str; content_digest:str; topic_tags:tuple[str,...]
    def __post_init__(self):
        for n in ("record_id","source_id","title","canonical_ref"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        object.__setattr__(self,"content_digest",_sha("content_digest",self.content_digest))
        tags=tuple(sorted({_token("topic_tag",v).lower() for v in self.topic_tags}))
        if not tags: raise LiteratureWatchError("topic_tags must be non-empty")
        object.__setattr__(self,"topic_tags",tags)
    @property
    def digest(self)->str:
        return _digest({"record_id":self.record_id,"source_id":self.source_id,"title":self.title,"canonical_ref":self.canonical_ref,"content_digest":self.content_digest,"topic_tags":list(self.topic_tags)})

@dataclass(frozen=True,slots=True)
class LiteratureTriage:
    record_digest:str; priority:str; matched_topics:tuple[str,...]; backlog_key:str|None; accepted:bool; external_side_effects:bool=False
    def __post_init__(self):
        object.__setattr__(self,"record_digest",_sha("record_digest",self.record_digest))
        priority=_token("priority",self.priority)
        if priority not in _PRIORITIES: raise LiteratureWatchError("unknown triage priority")
        object.__setattr__(self,"priority",priority)
        object.__setattr__(self,"matched_topics",tuple(sorted({_token("matched_topic",v) for v in self.matched_topics})))
        if self.backlog_key is not None: object.__setattr__(self,"backlog_key",_token("backlog_key",self.backlog_key))
        if not isinstance(self.accepted,bool): raise LiteratureWatchError("accepted must be boolean")
        if self.accepted and self.backlog_key is None: raise LiteratureWatchError("accepted literature requires backlog key")
        if self.external_side_effects is not False: raise LiteratureWatchError("triage cannot mutate backlog directly")

def triage_record(*,record:LiteratureRecord,source:LiteratureSource,watched_topics:Iterable[str],backlog_prefix:str)->LiteratureTriage:
    if record.source_id!=source.source_id: raise LiteratureWatchError("record/source identity mismatch")
    watched={_token("watched_topic",v).lower() for v in watched_topics}
    matched=tuple(sorted(set(record.topic_tags)&watched))
    accepted=bool(matched)
    priority="high" if accepted and source.trust_tier>=2 else ("normal" if accepted else "low")
    backlog_key=f"{_token('backlog_prefix',backlog_prefix)}:{record.content_digest[:16]}" if accepted else None
    return LiteratureTriage(record.digest,priority,matched,backlog_key,accepted)
