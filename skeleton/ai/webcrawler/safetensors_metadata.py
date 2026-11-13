"""Bounded safetensors tensor catalog from already acquired complete bytes.

The parser reads the small JSON header and compares declared tensor byte
offsets with payload framing. It never decodes tensor values, allocates
weight arrays, imports ML frameworks, loads network references, or grants
licensing/training permission. Declared metadata and tensor names are
never surfaced verbatim because these can embed secrets and addresses.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
import struct
from typing import Any

from .research_projection import ResearchFormatError,ResearchProjection,project_lines

SAFETENSORS_TYPES=frozenset({
    "application/vnd.safetensors","application/x-safetensors",
})
_MAX_BYTES=2_097_152
_MAX_HEADER=1_048_576
_MAX_TENSORS=512
_DTYPES={
    "BOOL":1,"U8":8,"I8":8,"F8_E4M3":8,"F8_E5M2":8,
    "U16":16,"I16":16,"F16":16,"BF16":16,
    "U32":32,"I32":32,"F32":32,
    "U64":64,"I64":64,"F64":64,
    "F4":4,"F6_E2M3":6,
}


def _unique(pairs:list[tuple[str,Any]])->dict:
    obj={}
    for name,value in pairs:
        if name in obj:
            raise ResearchFormatError("duplicate safetensors header key")
        obj[name]=value
    return obj


def _nonfinite(value:str):
    raise ResearchFormatError("nonfinite safetensors value")


def extract_safetensors(
    raw:bytes,*,max_chars:int=524288,
)->ResearchProjection:
    if (type(raw) is not bytes or not 10<=len(raw)<=_MAX_BYTES
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("safetensors source exceeds finite payload capacity")
    header_length=struct.unpack("<Q",raw[:8])[0]
    if not 2<=header_length<=_MAX_HEADER or 8+header_length>len(raw):
        raise ResearchFormatError("safetensors header length invalid")
    try:
        header=json.loads(raw[8:8+header_length].decode("utf-8","strict"),
                          object_pairs_hook=_unique,parse_constant=_nonfinite)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise ResearchFormatError("invalid safetensors JSON header") from exc
    if not isinstance(header,dict) or len(header)>_MAX_TENSORS+1:
        raise ResearchFormatError("safetensors tensor header object invalid")
    metadata=header.pop("__metadata__",{})
    if not isinstance(metadata,dict) or len(metadata)>128:
        raise ResearchFormatError("safetensors header metadata capacity exceeded")
    if any(not isinstance(key,str) or not isinstance(value,str)
           or len(key)>256 or len(value)>4096
           for key,value in metadata.items()):
        raise ResearchFormatError("unbounded safetensors string metadata")
    if not 1<=len(header)<=_MAX_TENSORS:
        raise ResearchFormatError("safetensors tensor catalog count invalid")
    tensor_bytes=len(raw)-(8+header_length)
    offsets=[]
    names=set()
    types=Counter()
    parameters=0
    declared=0
    for name,row in header.items():
        if (not isinstance(name,str) or not 1<=len(name)<=256
                or any(ord(ch)<32 for ch in name) or name in names):
            raise ResearchFormatError("safetensors tensor identity invalid")
        names.add(name)
        if not isinstance(row,dict) or set(row)!={"dtype","shape","data_offsets"}:
            raise ResearchFormatError("safetensors tensor map malformed")
        dtype=row["dtype"]
        if not isinstance(dtype,str) or dtype not in _DTYPES:
            raise ResearchFormatError("safetensors element dtype unsupported")
        shape=row["shape"]
        if (not isinstance(shape,list) or len(shape)>8
                or any(type(v) is not int or not 0<=v<=1000000000 for v in shape)):
            raise ResearchFormatError("safetensors tensor shape invalid")
        count=1
        for dim in shape:
            count*=dim
            if count>1_000_000_000:
                raise ResearchFormatError("safetensors parameter count exceeds cap")
        segment=row["data_offsets"]
        if (not isinstance(segment,list) or len(segment)!=2
                or any(type(v) is not int or v<0 or v>tensor_bytes for v in segment)
                or segment[0]>segment[1]):
            raise ResearchFormatError("safetensors data offset invalid")
        length=segment[1]-segment[0]
        expected=(count*_DTYPES[dtype]+7)//8
        if length!=expected:
            raise ResearchFormatError("safetensors dtype/shape byte length mismatch")
        offsets.append(tuple(segment))
        parameters+=count
        declared+=length
        if parameters>4_000_000_000:
            raise ResearchFormatError("safetensors aggregate parameters exceed cap")
        types[dtype]+=1
    offsets.sort()
    position=0
    for start,end in offsets:
        if start!=position:
            raise ResearchFormatError("safetensors tensor payload has overlaps/gaps")
        position=end
    if position!=tensor_bytes:
        raise ResearchFormatError("safetensors undeclared trailing tensor payload")
    metadata_size=header_length
    lines=[
        "ML artifact: bounded safetensors header (not model execution)",
        f"Tensor declarations: {len(header)}; scalar elements declared: {parameters}",
        f"Header bytes: {metadata_size}; tensor payload bytes: {declared}",
        "Element dtype counts: "+", ".join(f"{kind}={count}" for kind,count in sorted(types.items())),
        "Tensor names, training metadata, model weights and values: not projected",
        "Tensor bytes: structurally framed only, never decoded",
    ]
    return project_lines(lines,title="safetensors model metadata",max_chars=max_chars)
