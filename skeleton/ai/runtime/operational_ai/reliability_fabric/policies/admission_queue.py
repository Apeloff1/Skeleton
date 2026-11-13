"""Semantic admission_queue control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["depth"]>=d["ceiling"]: fail("admission queue saturated")
    if d["now_ns"]>=d["deadline_ns"]: fail("deadline passed before admission")
    if d["priority"]=="untrusted": fail("untrusted queue priority")
