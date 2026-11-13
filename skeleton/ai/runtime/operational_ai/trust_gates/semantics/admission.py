"""admission boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if p["now_ns"] >= p["deadline_ns"]: fail("deadline expired before admission")
    if p["queue_depth"] >= p["queue_ceiling"]: fail("bounded request queue saturated")
    if p["requested_tokens"] > p["token_ceiling"]: fail("operator token ceiling exceeded")
