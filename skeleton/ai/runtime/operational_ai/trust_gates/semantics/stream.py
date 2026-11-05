"""stream boundary semantics: fail closed on cross-field conflicts."""
from ..contracts import fail

def check(p):
    if any(c["index"] != pos for pos,c in enumerate(p["chunks"])): fail("noncontiguous stream sequence")
    if sum(len(c["text"].encode("utf-8")) for c in p["chunks"]) > p["max_bytes"]: fail("stream byte ceiling exceeded")
    if p["generated_tokens"] > p["token_ceiling"]: fail("native token bound exceeded")
