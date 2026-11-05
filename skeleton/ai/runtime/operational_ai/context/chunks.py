"""Deterministic source splitting with exact original character offsets."""
from __future__ import annotations
from dataclasses import dataclass
from ..authority.canonical import ContractViolation,digest
from .sources import Source


@dataclass(frozen=True,slots=True)
class Chunk:
    source_id:str
    source_sha256:str
    start:int
    end:int
    text:str
    chunk_sha256:str


def segment(source:Source,*,width:int=2048,overlap:int=32,
            maximum_chunks:int=256)->tuple[Chunk,...]:
    if type(width) is not int or not 128<=width<=8192:
        raise ContractViolation("invalid segment width")
    if type(overlap) is not int or not 0<=overlap<width:
        raise ContractViolation("invalid overlap budget")
    if type(maximum_chunks) is not int or not 1<=maximum_chunks<=256:
        raise ContractViolation("invalid number of segments")
    result=[]
    start=0
    while start<len(source.body):
        end=min(start+width,len(source.body))
        text=source.body[start:end]
        result.append(Chunk(source.source_id,source.digest,start,end,text,
                            digest({"source_id":source.source_id,"source_sha256":source.digest,
                                    "start":start,"end":end,"text":text})))
        if len(result)>maximum_chunks:
            raise ContractViolation("source requires more than admitted chunks")
        if end==len(source.body):break
        start=end-overlap
    return tuple(result)


def verify(source:Source,chunk:Chunk)->None:
    if chunk.source_id!=source.source_id or chunk.source_sha256!=source.digest:
        raise ContractViolation("chunk source identity mismatch")
    if source.body[chunk.start:chunk.end]!=chunk.text:
        raise ContractViolation("chunk offset content mismatch")
    expected=digest({"source_id":source.source_id,"source_sha256":source.digest,
                     "start":chunk.start,"end":chunk.end,"text":chunk.text})
    if expected!=chunk.chunk_sha256:
        raise ContractViolation("chunk evidence digest mismatch")
