"""Authoritative input checks for the key_rotation reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["new_epoch"]!=d["old_epoch"]+1: fail("key epoch rotation skip or fork")
    if not d["approved"]: fail("rotation authority missing")
    if not d["old_key_retired"]: fail("old key remains capable of issuance")
