"""Semantic retrieval_integrity control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["excerpt_sha"]!=d["observed_excerpt_sha"]: fail("retrieved span digest mismatch")
    if not d["start"]<d["end"]<=d["source_length"]: fail("invalid source byte interval")
    if d["source_sha"]!=p["approval"]["source_sha256"]: fail("retrieval source provenance unapproved")
