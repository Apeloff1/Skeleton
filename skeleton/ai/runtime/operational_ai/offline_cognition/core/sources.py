"""Strict document source receipts and exact-byte span accountability."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import identifier,sha,integer,text,hash_bytes,refuse
@dataclass(frozen=True,slots=True)
class Source:
    source_id:str
    tenant:str
    subject:str
    sha256:str
    bytes_length:int
    approved:bool
    def __post_init__(self):
        identifier(self.source_id);identifier(self.tenant);identifier(self.subject)
        sha(self.sha256);integer(self.bytes_length,minimum=1,maximum=2**32)
        if type(self.approved) is not bool:refuse("source approval must be explicit")
def bind_source(data,*,source_id,tenant,subject,approved):
    if type(data) is not bytes or not 1<=len(data)<=2**25:
        refuse("source bytes outside bounded limits")
    return Source(source_id,tenant,subject,hash_bytes(data),len(data),approved)
def extract_span(data,source,*,start,end,tenant,subject):
    if type(data) is not bytes or type(source) is not Source:
        refuse("untrusted source content")
    integer(start,maximum=2**32);integer(end,minimum=start+1,maximum=2**32)
    if source.tenant!=tenant or source.subject!=subject or not source.approved:
        refuse("cross-principal or unapproved source")
    if hash_bytes(data)!=source.sha256 or len(data)!=source.bytes_length:
        refuse("source content modified after receipt")
    if end>len(data):refuse("span outside original source")
    snippet=data[start:end]
    return {"source_id":source.source_id,"start":start,"end":end,
            "sha256":hash_bytes(snippet),"byte_length":len(snippet)}
