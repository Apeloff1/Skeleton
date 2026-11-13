"""tokenizer boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    ids=(p["bos_id"],p["eos_id"],p["unk_id"])
    if len(set(ids)) != 3 or max(ids) >= p["vocab_size"]: fail("special token identities overlap or exceed vocabulary")
    if p["normalization"] == "unknown": fail("normalization unattested")
    if p["context_window"] < 128: fail("context insufficient")
