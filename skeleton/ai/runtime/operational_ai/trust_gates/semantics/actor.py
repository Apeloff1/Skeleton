"""actor boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if p["scope"] != p["tenant"]+":"+p["user"]: fail("scope identity mismatch")
    if p["tenant"] in ("*","all","root") or p["user"] in ("*","all"): fail("wildcard principal")
    if "inference" not in p["rights"] or any(x not in ("inference","read") for x in p["rights"]): fail("actor authority escalation")
