"""cancel AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if p["state"]=="cancelled" and (not p["acked"] or p["backend_active"]): fail("cancelled request unacknowledged or active")
    if p["now_ns"]>=p["deadline_ns"] and p["state"]=="running": fail("expired request still running")
    if p["state"]=="complete" and p["backend_active"]: fail("completed work still running")
