"""Semantic weight_custody control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if sum(d["shards"])!=d["total_bytes"]: fail("model shard size reconciliation failed")
    if d["total_bytes"]>d["maximum_bytes"]: fail("weight bound exceeded")
    if d["manifest_sha"]!=p["approval"]["source_sha256"]: fail("unapproved manifest provenance")
