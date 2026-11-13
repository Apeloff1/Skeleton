"""Authoritative input checks for the canary_evidence reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if not d["native_executed"]: fail("not a real model canary")
    if d["model_sha"]!=p["identity"]["model_sha256"]: fail("canary did not run pinned model")
    if d["observed_tokens"]<1 or d["output_sha"]=="0"*64: fail("no native output observation")
