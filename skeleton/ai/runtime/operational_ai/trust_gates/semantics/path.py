"""path AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    path=p["relative_path"]
    if path.startswith("/") or chr(92) in path or chr(0) in path or any(x in ("",".","..") for x in path.split("/")): fail("unsafe relative path")
    if not path.endswith(p["suffix"]): fail("path suffix mismatch")
    if p["bytes"]>p["byte_limit"] or not p["immutable"]: fail("path custody unbounded or mutable")
