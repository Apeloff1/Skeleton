"""Semantic retry_budget control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["attempt"]>d["max_attempts"]: fail("retry ceiling reached")
    if not d["retryable"]: fail("nonretryable operation")
    if d["side_effect_committed"]: fail("retries after committed effects forbidden")
