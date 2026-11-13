"""conversation boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if p["messages"][-1]["role"] != "user": fail("non-user message at inference boundary")
    if p["final_role"] != p["messages"][-1]["role"]: fail("terminal role mismatch")
    if sum(len(m["content"].encode("utf-8")) for m in p["messages"]) > p["max_bytes"]: fail("history byte ceiling")
