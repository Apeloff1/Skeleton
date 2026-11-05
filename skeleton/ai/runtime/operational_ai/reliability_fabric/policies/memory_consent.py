"""Semantic memory_consent control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["source_tenant"]!=p["identity"]["tenant"]: fail("cross-tenant memory")
    if d["source_subject"]!=p["identity"]["subject"]: fail("cross-subject memory")
    if not d["approved"] or d["now_ns"]>=d["expires_ns"]: fail("memory consent absent or expired")
