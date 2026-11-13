"""Semantic cancellation control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["requested"] and not d["acknowledged"]: fail("unacknowledged native cancellation")
    if d["native_active"]: fail("native worker still active")
    if d["now_ns"]>=d["deadline_ns"]: fail("cancellation deadline passed")
