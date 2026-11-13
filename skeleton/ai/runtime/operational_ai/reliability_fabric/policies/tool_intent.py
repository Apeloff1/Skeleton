"""Authoritative input checks for the tool_intent reliability contract."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["tool"] not in ("read_text","list_files"): fail("write or external tool cannot be implied")
    if d["risk"]!="low": fail("high-risk model tool intent")
    if not d["approved"] or d["external_effect"]: fail("tool intent lacks authority or has effects")
