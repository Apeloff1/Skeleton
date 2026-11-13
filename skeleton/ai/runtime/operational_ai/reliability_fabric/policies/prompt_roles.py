"""Semantic prompt_roles control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["last_role"]!="user" or d["roles"][-1]!="user": fail("prompt not ended by actual user turn")
    if d["roles"][0]!="system": fail("canonical system authority missing")
    if d["tool_override"] or "tool" in d["roles"]: fail("untrusted tool role injected")
