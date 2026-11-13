"""Read-only checkpoint receipt from trusted, already-verified model metadata."""
from __future__ import annotations
from ..contracts import fail
from ..engine import validate

def inspect_checkpoint(manifest, *, operator_approval=False, max_bytes=20000000000):
    if type(manifest) is not dict:
        fail("checkpoint must be explicit manifest")
    if set(manifest)!={"model_id","model_sha","tokenizer_sha","format","bytes","step"}:
        fail("unknown checkpoint metadata field")
    payload={**manifest,"max_bytes":max_bytes,"approved":operator_approval}
    # The operator must still verify real on-disk model bytes with the
    # descriptor-anchored installer; this only checks provided metadata.
    return validate("checkpoint",payload)
