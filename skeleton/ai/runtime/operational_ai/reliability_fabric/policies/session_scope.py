"""Semantic session_scope control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["tenant"]!=p["identity"]["tenant"]: fail("cross-tenant session")
    if d["subject"]!=p["identity"]["subject"]: fail("cross-subject session")
    if d["closed"] or d["scope"]!=d["tenant"]+":"+d["subject"]: fail("invalid or closed session scope")
