"""Semantic output_receipt control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["declared_sha"]!=d["observed_sha"]: fail("output bytes differ from committed digest")
    if d["generated_tokens"]>d["max_generated"]: fail("native response token budget exceeded")
    if d["finish_reason"]=="unknown": fail("native finish reason is unrecognized")
