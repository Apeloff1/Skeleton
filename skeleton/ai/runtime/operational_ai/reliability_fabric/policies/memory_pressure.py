"""Semantic memory_pressure control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if not d["memory_known"]: fail("unknown memory telemetry")
    if d["available"]<d["needed"]: fail("insufficient observed memory")
    if d["swap_allowed"]: fail("unapproved swap fallback")
