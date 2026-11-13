"""retrieval AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    import hashlib
    raw=p["text"].encode("utf-8")
    if p["span_end"]<=p["span_start"] or raw[p["span_start"]:p["span_end"]]!=p["excerpt"].encode("utf-8"): fail("byte span mismatch")
    if hashlib.sha256(raw).hexdigest()!=p["source_sha"]: fail("retrieval source hash mismatch")
    if not p["approved"]: fail("unapproved retrieval source")
