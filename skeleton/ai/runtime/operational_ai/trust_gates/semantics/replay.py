"""replay AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if p["model_sha"]!=p["expected_model_sha"]: fail("model epoch changed for replay")
    if p["replayed"] and p["request_digest"]!=p["stored_digest"]: fail("replay request fingerprint conflict")
    if p["replayed"] and p["has_generation"]: fail("idempotent replay invoked generation")
