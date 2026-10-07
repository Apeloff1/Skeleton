"""Typed cryptographic commitments for durable AI provenance.

Bare digest strings are deliberately avoided at interchange boundaries. Every
commitment names its algorithm and canonicalization profile so future readers
never have to infer cryptographic meaning from string length.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Final

PROFILE: Final = "skeleton.canonical-json.v1"
ALGORITHMS: Final = ("sha256","sha3-256","blake2b-256")

def canonical_bytes(value: object) -> bytes:
    def check(v: object) -> None:
        if v is None or isinstance(v,(str,bool,int)): return
        if isinstance(v,float): raise ValueError("canonical profile forbids floating point values")
        if isinstance(v,(list,tuple)):
            for x in v: check(x)
            return
        if isinstance(v,dict):
            if any(not isinstance(k,str) for k in v): raise ValueError("canonical map keys must be strings")
            for x in v.values(): check(x)
            return
        raise TypeError("unsupported canonical value")
    check(value)
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")

def hash_bytes(data: bytes, algorithm: str) -> str:
    if algorithm=="sha256": return hashlib.sha256(data).hexdigest()
    if algorithm=="sha3-256": return hashlib.sha3_256(data).hexdigest()
    if algorithm=="blake2b-256": return hashlib.blake2b(data,digest_size=32).hexdigest()
    raise ValueError("unsupported digest algorithm")

@dataclass(frozen=True,slots=True)
class Commitment:
    algorithm: str
    value: str
    profile: str = PROFILE
    def __post_init__(self)->None:
        if self.algorithm not in ALGORITHMS: raise ValueError("unsupported digest algorithm")
        if self.profile!=PROFILE: raise ValueError("unsupported canonicalization profile")
        if len(self.value)!=64 or any(c not in "0123456789abcdef" for c in self.value): raise ValueError("invalid 256-bit digest")
    def to_dict(self)->dict[str,str]:
        return {"algorithm":self.algorithm,"value":self.value,"profile":self.profile}
    @classmethod
    def of(cls,value: object,algorithm: str="sha256")->"Commitment":
        return cls(algorithm,hash_bytes(canonical_bytes(value),algorithm))

__all__=["ALGORITHMS","PROFILE","Commitment","canonical_bytes","hash_bytes"]
