"""Authoritative input checks for the restore_order reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if not d["inventory"] or not d["keys"]: fail("restore source or key integrity not proved")
    if not d["journal"] or not d["chat"]: fail("state and journal recovery mismatch")
    if not d["approved"]: fail("operator restore approval missing")
