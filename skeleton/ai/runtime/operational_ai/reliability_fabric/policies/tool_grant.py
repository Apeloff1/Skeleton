"""Semantic tool_grant control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["tool"] not in ("read_text","list_files"): fail("non-read-only tool grant")
    if d["scope"]!=p["identity"]["subject"]+":"+d["tool"]: fail("tool grant scope mismatch")
    if d["write_allowed"] or d["now_ns"]>=d["expires_ns"]: fail("tool grant escalated or expired")
