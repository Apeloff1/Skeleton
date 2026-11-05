"""Semantic memory_deletion control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["owner"]!=p["identity"]["subject"]: fail("deletion owner mismatch")
    if not d["tombstoned"]: fail("deletion tombstone missing")
    if d["materialized"] or d["replicas_pending"]!=0: fail("memory deletion not fully propagated")
