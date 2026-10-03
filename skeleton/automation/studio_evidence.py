"""Canonical hashing primitives for Studio evidence."""
from __future__ import annotations
import hashlib, json
from typing import Any

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode("utf-8")

def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def chain(previous: str, event: Any) -> str:
    if previous and (len(previous)!=64 or any(c not in "0123456789abcdef" for c in previous)):
        raise ValueError("previous evidence hash malformed")
    return hashlib.sha256(previous.encode()+canonical_bytes(event)).hexdigest()
