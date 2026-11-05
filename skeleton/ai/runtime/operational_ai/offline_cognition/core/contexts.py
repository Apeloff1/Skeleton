"""Real token-budget allocation with model-count authority kept separate."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import identifier,integer,refuse,hash_bytes
from .budget import partition
@dataclass(frozen=True,slots=True)
class ContextSlice:
    source_id:str
    role:str
    byte_sha256:str
    token_count:int
    priority:int
    mandatory:bool=False
    def __post_init__(self):
        identifier(self.source_id)
        if self.role not in ("system","developer","user","history","retrieval"):
            refuse("context source role not allowlisted")
        from .contracts import sha
        sha(self.byte_sha256)
        integer(self.token_count,minimum=1,maximum=262144)
        integer(self.priority,minimum=0,maximum=100000)
        if type(self.mandatory) is not bool:refuse("explicit mandatory bit required")
def pack(slices,*,window,output_reserved,safety_reserved=32):
    integer(window,minimum=128,maximum=262144)
    integer(output_reserved,minimum=1,maximum=65536)
    integer(safety_reserved,maximum=65536)
    capacity=window-output_reserved-safety_reserved
    if capacity<=0:refuse("no available prompt tokens")
    if type(slices) not in (tuple,list) or not 1<=len(slices)<=4096:
        refuse("bounded explicit context evidence required")
    if len({s.source_id for s in slices})!=len(slices):
        refuse("ambiguous context source identity")
    mandatory=[s for s in slices if s.mandatory]
    optional=[s for s in slices if not s.mandatory]
    used=sum(s.token_count for s in mandatory)
    if used>capacity:refuse("mandatory system/user context cannot be truncated")
    selected=mandatory[:];omitted=[]
    for slice in sorted(optional,key=lambda x:(-x.priority,x.source_id)):
        if used+slice.token_count<=capacity:
            selected.append(slice);used+=slice.token_count
        else:omitted.append(slice.source_id)
    if not any(s.role=="user" for s in selected):
        refuse("context lost authoritative user turn")
    if not any(s.role=="system" for s in selected):
        refuse("context lost system policy")
    return {"selected":tuple(s.source_id for s in selected),
            "omitted":tuple(omitted),"tokens":used,
            "capacity":capacity,"native_count_attested":False}
def sliding_history(rows,*,last_n=32,byte_budget=131072):
    integer(last_n,minimum=1,maximum=4096)
    integer(byte_budget,minimum=1,maximum=2**24)
    if type(rows) not in (tuple,list) or len(rows)>10000:
        refuse("unbounded history input")
    selected=[];bytes_used=0
    for item in reversed(rows):
        if type(item) is not dict or set(item)!={"role","text","sha256"}:
            refuse("history row is not exact schema")
        if item["role"] not in ("user","assistant"):refuse("untrusted history role")
        raw=item["text"].encode("utf-8","strict")
        if hash_bytes(raw)!=item["sha256"]:refuse("history content digest mismatch")
        if bytes_used+len(raw)>byte_budget or len(selected)==last_n:break
        selected.append(item);bytes_used+=len(raw)
    return tuple(reversed(selected))
