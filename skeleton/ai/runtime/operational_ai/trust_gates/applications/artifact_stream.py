"""Bounded chunk hashing against a caller-pinned model manifest.

Input is an already-opened, authorized byte stream: this does not replace the
descriptor-anchored, symlink-safe filesystem installer.
"""
from __future__ import annotations
import hashlib
from ..contracts import GateViolation, fail
from ..engine import validate

def verify_chunks(*, model_id, chunks, expected_digest, expected_bytes,
                  license, source, approved, max_chunk=64*1024*1024):
    if type(max_chunk) is not int or not 1<=max_chunk<=64*1024*1024:
        fail("bad artifact chunk ceiling")
    if type(expected_bytes) is not int or not 1<=expected_bytes<=20_000_000_000:
        fail("invalid approved model length")
    hasher=hashlib.sha256()
    sizes=[]
    total=0
    for chunk in chunks:
        if type(chunk) is not bytes or not 1<=len(chunk)<=max_chunk:
            fail("invalid model chunk")
        if len(sizes)>=64 or total+len(chunk)>expected_bytes:
            fail("bounded model stream exceeded")
        hasher.update(chunk)
        sizes.append(len(chunk))
        total+=len(chunk)
    if total!=expected_bytes:
        fail("model input ended before exact declared length")
    observed=hasher.hexdigest()
    if observed!=expected_digest:
        fail("model source digest differs from approved manifest")
    payload={"model_id":model_id,"digest":observed,"bytes":total,
             "shard_bytes":sizes,"license":license,"source":source,
             "approved":approved}
    return validate("artifact",payload)
