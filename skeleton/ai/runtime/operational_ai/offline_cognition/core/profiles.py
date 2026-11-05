"""Closed operational family profiles: no model text can create capabilities."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from .contracts import identifier,integer,number,sha,exact,loads,fingerprint,refuse
_ALLOWED=frozenset(("source","search","fusion","rank","context","plan",
    "resource","schedule","permission","native","replay","memory",
    "privacy","evaluate","audit","recover","stream","tool","checkpoint","health"))
@dataclass(frozen=True,slots=True)
class Profile:
    name:str
    category:str
    source_role:str
    retrieval_mode:str
    context_limit:int
    byte_limit:int
    latency_ms:int
    min_evidence:int
    priority:int
    rank_lexical:float
    rank_dense:float
    rank_freshness:float
    operations:tuple[str,...]
    def __post_init__(self):
        identifier(self.name);identifier(self.category)
        if self.source_role not in ("system","user","retrieval","history"):
            refuse("invalid domain authority role")
        if self.retrieval_mode not in ("lexical","dense","hybrid"):
            refuse("unrecognized retrieval mode")
        integer(self.context_limit,minimum=128,maximum=262144)
        integer(self.byte_limit,minimum=1024,maximum=262144)
        integer(self.latency_ms,minimum=50,maximum=3600000)
        integer(self.min_evidence,minimum=1,maximum=100)
        integer(self.priority,maximum=10000)
        weights=(self.rank_lexical,self.rank_dense,self.rank_freshness)
        for score in weights:number(score,minimum=0,maximum=1)
        if abs(sum(weights)-1)>1e-9:refuse("source ranking weights do not sum to one")
        if (type(self.operations) is not tuple or len(self.operations)!=len(_ALLOWED)
            or set(self.operations)!=_ALLOWED):
            refuse("operational domain must enumerate every bounded boundary")
    @classmethod
    def parse(cls,data):
        expected={"name","category","source_role","retrieval_mode","context_limit",
                  "byte_limit","latency_ms","min_evidence","priority",
                  "rank_lexical","rank_dense","rank_freshness","operations"}
        exact(data,expected)
        return cls(**{k:(tuple(v) if k=="operations" else v) for k,v in data.items()})
    def receipt(self):
        return {"name":self.name,"category":self.category,
            "context_limit":self.context_limit,"byte_limit":self.byte_limit,
            "latency_ms":self.latency_ms,"min_evidence":self.min_evidence,
            "priority":self.priority,"rank_weights":(self.rank_lexical,
            self.rank_dense,self.rank_freshness)}
@lru_cache(maxsize=128)
def read_profile(name):
    identifier(name)
    root=resources.files("skeleton.ai.runtime.operational_ai.offline_cognition")
    raw=root.joinpath("families",name,"profile.json").read_bytes()
    value=loads(raw,maximum=16384)
    if value.get("name")!=name:refuse("directory/profile name mismatch")
    return Profile.parse(value)
