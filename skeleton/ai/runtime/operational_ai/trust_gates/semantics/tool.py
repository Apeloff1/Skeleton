"""Read-only tool invocation guards: caller-approved, low risk, no path escape."""
from ..contracts import fail

def check(p):
    if p["tool_id"] not in ("read_text","list_files"):
        fail("tool not read-only")
    if p["risk"]!="low" or not p["approved"]:
        fail("tool risk or caller approval insufficient")
    path=p["args"]["path"]
    if path.startswith("/") or chr(92) in path or chr(0) in path:
        fail("tool path escapes lexical sandbox")
    if any(component in ("",".","..") for component in path.split("/")):
        fail("tool parent/current/empty component refused")
