"""evaluation AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if p["samples"]==0: fail("empty evaluation")
    if p["samples"]!=p["passes"]+p["failures"]+p["empty_errors"]: fail("evaluation count mismatch")
    if not p["approved"]: fail("evaluation provenance unapproved")
