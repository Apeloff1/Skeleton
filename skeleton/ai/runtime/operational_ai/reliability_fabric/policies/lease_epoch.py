"""Authoritative input checks for the lease_epoch reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["owner_epoch"]!=d["observed_epoch"]: fail("stale lease owner epoch")
    if not d["live"]: fail("expired or revoked lease")
    if d["now_ns"]>=d["expires_ns"]: fail("lease time window exhausted")
