"""grant boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if p["now"] >= p["expires_at"]: fail("grant expired")
    if p["rights"] != ["read"]: fail("grant exceeds read-only authority")
    if p["scope"] != p["actor_id"]+":"+p["tool_id"]: fail("grant scope mismatch")
