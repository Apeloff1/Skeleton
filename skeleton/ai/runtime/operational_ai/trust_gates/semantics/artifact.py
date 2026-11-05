"""artifact boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if sum(p["shard_bytes"]) != p["bytes"]: fail("shard bytes mismatch")
    if not p["approved"]: fail("artifact provenance unapproved")
    if p["license"].lower() in ("unknown","unreviewed","none"): fail("license unspecified")
