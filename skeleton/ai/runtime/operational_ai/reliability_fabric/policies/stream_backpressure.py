"""Semantic stream_backpressure control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["sent"]-d["acknowledged"]-1>d["window"]: fail("stream credit exceeded")
    if d["acknowledged"]>=d["sent"]: fail("acknowledged frame was never sent")
    if d["bytes_out"]>p["limits"]["bytes"]: fail("stream bytes overrun")
