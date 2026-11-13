"""Tokenizer tests."""
from skeleton.jeeves.ecosystem.tokenizers.script_tokenizer import tokenize, embed

def test_tokenize():
    toks = tokenize("hello world", 8)
    assert len(toks) <= 8
    assert all(isinstance(t, int) for t in toks)

def test_embed():
    e = embed("platformer")
    assert len(e) == 8
