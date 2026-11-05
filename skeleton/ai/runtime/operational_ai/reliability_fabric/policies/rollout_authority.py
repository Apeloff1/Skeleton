"""Authoritative input checks for the rollout_authority reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if not d["reviewed"]: fail("independent review missing")
    if d["ci_success"]!=d["ci_total"] or d["ci_total"]!=10: fail("required exact-head gate set incomplete")
    if not d["operator_approved"]: fail("unapproved model rollout")
