"""transport AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if p["host"] not in ("127.0.0.1","::1"): fail("non-loopback exposure")
    if p["method"]!="POST" or p["auth_type"]!="bearer": fail("unauthenticated transport")
    if p["token_bytes"]<32 or p["body_bytes"]>p["body_ceiling"]: fail("transport bounds exceeded")
    if p["content_type"]!="application/json": fail("non-JSON content type")
