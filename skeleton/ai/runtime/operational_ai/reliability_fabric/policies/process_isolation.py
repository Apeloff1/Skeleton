"""Authoritative input checks for the process_isolation reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if not d["isolated"]: fail("native model not isolated")
    if d["child_pid"]<=0: fail("no verifiable native process")
    if not d["exit_observed"]: fail("native process termination not proved")
