"""Authoritative input checks for the transport_local reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["host"] not in ("127.0.0.1","::1"): fail("non-loopback model service")
    if d["method"]!="POST": fail("unsupported remote operation method")
    if d["bearer_bytes"]<32 or d["origin_present"]: fail("missing bearer or browser origin attack")
