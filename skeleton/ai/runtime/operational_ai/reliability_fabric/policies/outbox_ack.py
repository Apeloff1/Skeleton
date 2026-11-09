"""Authoritative input checks for the outbox_ack reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["event_sha"]!=d["ack_sha"]: fail("outbox acknowledgment digest conflict")
    if not d["delivered"]: fail("undelivered event cannot be acknowledged")
    if d["duplicate"]: fail("duplicate outbox effect cannot be asserted as new")
