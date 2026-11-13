"""Semantic citation_provenance control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["document_sha"]!=p["approval"]["source_sha256"]: fail("citation source identity mismatch")
    if not d["cited"]: fail("unsupported citation claim")
    if d["untrusted_as_instruction"]: fail("retrieved source promoted to instruction")
