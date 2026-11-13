"""Authoritative input checks for the evaluation_evidence reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["samples"]!=d["passes"]+d["failures"]+d["unknown"]: fail("evaluation tally mismatch")
    if d["unknown"]!=0 or not d["samples"]: fail("incomplete evaluation evidence")
    if d["dataset_sha"]!=p["approval"]["source_sha256"]: fail("evaluation dataset identity changed")
