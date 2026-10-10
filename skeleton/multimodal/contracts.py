"""Typed, provenance-bound multimodal ingestion contracts."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import re
from types import MappingProxyType
from typing import Mapping

from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes

MAX_SEGMENTS=4096
MAX_TEXT=1_000_000
_SHA=re.compile(r"^[0-9a-f]{64}$")

class MediaError(ValueError): pass
class Modality(str,Enum): DOCUMENT="document"; IMAGE="image"; AUDIO="audio"; SPEECH="speech"; VIDEO="video"

def _token(v:str,n:str,m=512):
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>m: raise MediaError(f"invalid {n}")
    return v
def _hex(v:str,n:str):
    if not isinstance(v,str) or not _SHA.fullmatch(v): raise MediaError(f"invalid {n}")
    return v
def _digest(v:object)->str:
    try: raw=canonical_json_bytes(v)
    except CanonicalContractError as exc: raise MediaError("media contract payload must be canonical JSON") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True,slots=True)
class MediaProvenance:
    source_id:str; source_digest:str; transform_digest:str|None=None
    def __post_init__(self):
        _token(self.source_id,"source_id"); _hex(self.source_digest,"source_digest")
        if self.transform_digest is not None: _hex(self.transform_digest,"transform_digest")
    @property
    def digest(self): return _digest({"source_id":self.source_id,"source_digest":self.source_digest,"transform_digest":self.transform_digest})

@dataclass(frozen=True,slots=True)
class ModalitySegment:
    segment_id:str; modality:Modality; payload_digest:str; provenance:MediaProvenance; text:str|None=None; untrusted_metadata:Mapping[str,str]|None=None
    def __post_init__(self):
        _token(self.segment_id,"segment_id",128)
        if not isinstance(self.modality,Modality): raise MediaError("invalid modality")
        _hex(self.payload_digest,"payload_digest")
        if not isinstance(self.provenance,MediaProvenance): raise MediaError("typed provenance required")
        if self.text is not None and (not isinstance(self.text,str) or len(self.text)>MAX_TEXT): raise MediaError("invalid text")
        md={} if self.untrusted_metadata is None else self.untrusted_metadata
        if not isinstance(md,Mapping) or len(md)>128: raise MediaError("metadata budget exceeded")
        clean={}
        for k,v in md.items(): clean[_token(k,"metadata key",128)]=_token(v,"metadata value",2048)
        object.__setattr__(self,"untrusted_metadata",MappingProxyType(dict(sorted(clean.items()))))
    @property
    def digest(self): return _digest({"segment_id":self.segment_id,"modality":self.modality.value,"payload_digest":self.payload_digest,"provenance":self.provenance.digest,"text":self.text,"untrusted_metadata":dict(self.untrusted_metadata)})

@dataclass(frozen=True,slots=True)
class CrossModalReference:
    source_segment_id:str; target_segment_id:str; relation:str; confidence:float
    def __post_init__(self):
        _token(self.source_segment_id,"source"); _token(self.target_segment_id,"target"); _token(self.relation,"relation",128)
        if self.source_segment_id==self.target_segment_id: raise MediaError("self reference")
        if isinstance(self.confidence,bool) or not isinstance(self.confidence,(int,float)) or not 0<=float(self.confidence)<=1: raise MediaError("invalid confidence")
    @property
    def digest(self): return _digest({"source":self.source_segment_id,"target":self.target_segment_id,"relation":self.relation,"confidence":float(self.confidence)})

@dataclass(frozen=True,slots=True)
class MediaArtifact:
    artifact_id:str; segments:tuple[ModalitySegment,...]; references:tuple[CrossModalReference,...]=(); authority_scope:str="untrusted-media-evidence"
    def __post_init__(self):
        _token(self.artifact_id,"artifact_id")
        if not isinstance(self.segments,tuple) or not self.segments or len(self.segments)>MAX_SEGMENTS: raise MediaError("segment budget")
        ids={}; 
        for s in self.segments:
            if not isinstance(s,ModalitySegment) or s.segment_id in ids: raise MediaError("invalid or duplicate segment")
            ids[s.segment_id]=s
        if not isinstance(self.references,tuple): raise MediaError("references must be tuple")
        for r in self.references:
            if not isinstance(r,CrossModalReference) or r.source_segment_id not in ids or r.target_segment_id not in ids: raise MediaError("dangling reference")
        if self.authority_scope!="untrusted-media-evidence": raise MediaError("media cannot grant policy authority")
        object.__setattr__(self,"segments",tuple(sorted(self.segments,key=lambda x:x.segment_id)))
        object.__setattr__(self,"references",tuple(sorted(self.references,key=lambda x:(x.source_segment_id,x.target_segment_id,x.relation))))
    @property
    def digest(self): return _digest({"artifact_id":self.artifact_id,"segments":[s.digest for s in self.segments],"references":[r.digest for r in self.references],"authority_scope":self.authority_scope})
