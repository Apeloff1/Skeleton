"""checkpoint AI trust-boundary cross-field checks; no model execution."""
from ..contracts import fail

def check(p):
    if not p["approved"]: fail("unapproved checkpoint")
    if p["bytes"]>p["max_bytes"]: fail("checkpoint exceeds declared size")
    if p["model_sha"]=="0"*64 or p["tokenizer_sha"]=="0"*64: fail("empty checkpoint identity")
    if p["format"] not in ("native-v1","gguf-v3"): fail("unknown model format")
