"""Semantic context_packing control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if sum(d[k] for k in ("system_tokens","user_tokens","history_tokens","retrieval_tokens","reserved_output"))>d["window"]: fail("context total exceeds window")
    if d["reserved_output"]>=d["window"]: fail("output consumes entire native context")
    if d["window"]>p["limits"]["tokens"]*4: fail("context exceeds operator reservation")
