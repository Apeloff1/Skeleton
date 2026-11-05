"""Derived output chunks with monotonic offsets and final digest."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import ServingError,hash_bytes
from .output import safe_output

@dataclass(frozen=True,slots=True)
class Chunk:
    seq:int
    start:int
    end:int
    body:str
    final_sha256:str|None


def chunk_response(text:str,size:int=4096)->tuple[Chunk,...]:
    safe_output(text)
    if type(size) is not int or not 1<=size<=16384:raise ServingError('chunk byte ceiling invalid')
    data=text.encode('utf8');chunks=[];cursor=0
    while cursor<len(data):
        end=min(cursor+size,len(data))
        while end>cursor:
            try:part=data[cursor:end].decode('utf8');break
            except UnicodeDecodeError:end-=1
        if end==cursor:raise ServingError('chunk size cannot contain one UTF-8 codepoint')
        chunks.append(Chunk(len(chunks),cursor,end,part,None));cursor=end
    final=hash_bytes(data)
    if not chunks:return (Chunk(0,0,0,'',final),)
    last=chunks[-1]
    chunks[-1]=Chunk(last.seq,last.start,last.end,last.body,final)
    return tuple(chunks)
