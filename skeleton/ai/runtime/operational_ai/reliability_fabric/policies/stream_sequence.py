"""Semantic stream_sequence control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["frame_count"]!=d["end_index"]-d["start_index"]+1: fail("stream has gap or overlap")
    if d["start_index"]!=0: fail("stream must begin at zero")
    if d["duplicate"]: fail("stream replay duplicates chunks")
