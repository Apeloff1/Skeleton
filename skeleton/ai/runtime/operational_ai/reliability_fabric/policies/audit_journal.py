"""Authoritative input checks for the audit_journal reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["sequence"]<1: fail("journal sequence absent")
    if d["previous_sha"]==d["current_sha"]: fail("journal self reference")
    if not d["verified"]: fail("journal content proof missing")
