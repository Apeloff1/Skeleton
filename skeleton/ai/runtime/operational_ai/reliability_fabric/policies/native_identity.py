"""Semantic native_identity control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if d["installed_sha"]!=p["identity"]["model_sha256"]: fail("installed model identity mismatch")
    if d["loaded_sha"]!=d["installed_sha"]: fail("native model differs from installed source")
    if not d["rights_approved"] or d["tokenizer_sha"]=="0"*64: fail("model rights or tokenizer not attested")
