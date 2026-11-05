"""Semantic request_dedupe control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["prior_digest"]!=d["incoming_digest"]: fail("idempotency key conflict")
    if d["regenerate"]: fail("committed request must not regenerate")
    if d["prior_state"]!="committed": fail("unresolved prior request needs durable recovery")
