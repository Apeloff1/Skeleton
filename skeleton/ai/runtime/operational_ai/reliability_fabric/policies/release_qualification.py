"""Authoritative input checks for the release_qualification reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["gates_passed"]!=d["gates_required"] or d["gates_required"]!=10: fail("required CI matrix incomplete")
    if not d["real_model_e2e"] or not d["device_tested"]: fail("no real laptop/model qualification")
    if not d["rights"]: fail("model licensing approval missing")
