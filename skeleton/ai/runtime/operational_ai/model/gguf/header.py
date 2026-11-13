"""Bounded GGUF header inspection prior to invoking a native inference library."""
from __future__ import annotations
from dataclasses import dataclass
import os
import struct
from .manifest import GGUFManifestError

@dataclass(frozen=True,slots=True)
class GGUFHeader:
    version:int
    tensors:int
    metadata_keys:int
    magic:bytes=b'GGUF'


def inspect_header(fd:int)->GGUFHeader:
    position=os.lseek(fd,0,os.SEEK_CUR)
    try:
        raw=os.pread(fd,24,0)
        if len(raw)!=24 or raw[:4]!=b'GGUF':
            raise GGUFManifestError("invalid or truncated GGUF header")
        version=struct.unpack_from('<I',raw,4)[0]
        if version not in (2,3):
            raise GGUFManifestError("unsupported GGUF file version")
        tensor_count,kv_count=struct.unpack_from('<QQ',raw,8)
        if tensor_count<=0 or tensor_count>20_000_000:
            raise GGUFManifestError("implausible GGUF tensor count")
        if kv_count<=0 or kv_count>100_000:
            raise GGUFManifestError("implausible GGUF metadata count")
        if os.fstat(fd).st_size<=24:
            raise GGUFManifestError("missing GGUF tensor and metadata body")
        return GGUFHeader(version,tensor_count,kv_count)
    finally:
        os.lseek(fd,position,os.SEEK_SET)
