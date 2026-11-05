"""journal AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if p["sequence"]==1 and p["prev_sha"]!="0"*64: fail("bad journal genesis parent")
    if p["sequence"]>1 and p["prev_sha"]=="0"*64: fail("journal parent absent")
    if p["event_sha"]==p["prev_sha"]: fail("self-referential journal event")
    if p["kind"] not in ("inference.completed","inference.refused","memory.admitted","memory.forgotten","tool.refused"): fail("unknown journal event kind")
