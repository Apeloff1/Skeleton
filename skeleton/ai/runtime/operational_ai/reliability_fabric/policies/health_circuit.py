"""Authoritative input checks for the health_circuit reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["failed"]>=d["max_failed"]: fail("inference circuit failure ceiling reached")
    if d["open"]: fail("open health circuit")
    if not d["cooldown_done"]: fail("health breaker cooldown pending")
