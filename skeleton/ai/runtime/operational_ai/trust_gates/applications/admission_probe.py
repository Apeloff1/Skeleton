"""Monotonic-time admission receipt with explicit queue saturation refusal."""
from __future__ import annotations
import time
from ..contracts import fail
from ..engine import validate

def inspect_admission(*, tenant,deadline_ns,queue_depth,queue_ceiling,
                      requested_tokens,token_ceiling,clock=time.monotonic_ns):
    if not callable(clock): fail("invalid admission clock")
    now=clock()
    if type(now) is not int:
        fail("monotonic clock must return integer")
    return validate("admission",{
        "tenant":tenant,"deadline_ns":deadline_ns,"now_ns":now,
        "queue_depth":queue_depth,"queue_ceiling":queue_ceiling,
        "requested_tokens":requested_tokens,"token_ceiling":token_ceiling})
