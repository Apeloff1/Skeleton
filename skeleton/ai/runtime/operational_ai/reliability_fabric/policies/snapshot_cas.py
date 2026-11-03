"""Authoritative input checks for the snapshot_cas reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["next_revision"]!=d["base_revision"]+1: fail("snapshot compare-and-set version fork")
    if d["checkpoint_sha"]=="0"*64: fail("missing snapshot digest")
    if d["dirty"]: fail("dirty snapshot publication forbidden")
