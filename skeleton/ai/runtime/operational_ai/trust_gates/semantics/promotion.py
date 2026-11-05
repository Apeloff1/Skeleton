"""promotion AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if any(s!="success" for s in p["checks"].values()): fail("required final-head workflow not successful")
    if not all(p[k] for k in ("independent_review","real_model_e2e","model_rights","installation")): fail("release evidence incomplete")
    if p["head_sha"]=="0"*64: fail("unbound promotion head")
