"""Versioned content-defined byte chunking for exact Hoarder manifest copies.

Boundaries use a deterministic gear table and bounded minimum/maximum spans.
Original bytes are never normalized, edited or dropped. The existing manifest
ledger, compression and reference-counted garbage collection own persistence.
"""
from __future__ import annotations

import hashlib
import json

MIN_CHUNK=32*1024
AVG_CHUNK=64*1024
MAX_CHUNK=256*1024
MAX_BYTES=4*1024*1024
MAX_CHUNKS=512
SCHEMA="dragon.hoarder.gear32.v1"
GEAR=tuple(int.from_bytes(hashlib.blake2s(bytes([n]),digest_size=4,
                    person=b"DRGNgear").digest(),"little") for n in range(256))


def lengths(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES:
        raise ValueError("content-defined copy exceeds checkpoint bound")
    start=0;state=0;out=[]
    for i,byte in enumerate(raw):
        state=((state<<1)+GEAR[byte])&0xffffffff
        size=i+1-start
        if size>=MIN_CHUNK and ((state&(AVG_CHUNK-1))==0 or size>=MAX_CHUNK):
            out.append(size);start=i+1;state=0
    if start<len(raw):out.append(len(raw)-start)
    return validate_lengths(out,len(raw))


def validate_lengths(value,expected):
    if (not isinstance(value,(list,tuple)) or not 1<=len(value)<=MAX_CHUNKS
            or type(expected) is not int or not 1<=expected<=MAX_BYTES
            or any(type(x) is not int or not 1<=x<=MAX_CHUNK for x in value)
            or any(x<MIN_CHUNK for x in value[:-1]) or sum(value)!=expected):
        raise ValueError("invalid content-defined layout")
    return tuple(value)


def encode_layout(value,expected):
    sizes=validate_lengths(value,expected)
    payload=json.dumps(list(sizes),separators=(",",":"))
    witness=hashlib.sha256((SCHEMA+":"+str(expected)+":"+payload).encode()).hexdigest()
    return payload,witness


def decode_layout(payload,witness,expected):
    if not isinstance(payload,str) or len(payload)>8192:
        raise ValueError("invalid content-defined layout envelope")
    try:value=json.loads(payload)
    except (ValueError,RecursionError) as exc:raise ValueError("invalid content-defined layout") from exc
    encoded,actual=encode_layout(value,expected)
    if payload!=encoded or witness!=actual:
        raise ValueError("content-defined layout witness changed")
    return tuple(value)


def split(raw,layout):
    sizes=validate_lengths(layout,len(raw))
    offset=0
    for size in sizes:
        yield raw[offset:offset+size]
        offset+=size
