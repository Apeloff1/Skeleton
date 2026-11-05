"""Authoritative input checks for the privacy_boundary reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["plaintext_logged"]: fail("private prompt leaked in telemetry")
    if d["token_logged"]: fail("bearer or local key leaked")
    if d["telemetry_fields"]>16 or not d["consent"]: fail("unbounded telemetry or no consent")
