"""Semantic tokenizer_custody control, executed after closed-schema validation."""
from ..contracts import fail

def check(p):
    d=p["details"]
    if len({d["bos"],d["eos"],d["unk"]})!=3: fail("special token identities overlap")
    if max(d["bos"],d["eos"],d["unk"])>=d["vocab"]: fail("special token ID outside vocabulary")
    if d["prompt_reservation"]>=d["context_window"]: fail("tokenizer context reservation overflow")
