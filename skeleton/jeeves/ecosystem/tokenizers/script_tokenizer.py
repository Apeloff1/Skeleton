"""script tokenizer — bounded, deterministic token ids.
"""
from __future__ import annotations

VOCAB_SIZE = 4096

def tokenize(text: str, max_tokens: int = 128) -> list[int]:
    if not isinstance(text, str) or not text:
        return []
    max_tokens = max(1, min(512, int(max_tokens)))
    tokens = []
    for i, ch in enumerate(text[:max_tokens * 4]):
        tokens.append((ord(ch) * 31 + i) % VOCAB_SIZE)
        if len(tokens) >= max_tokens:
            break
    return tokens

def detokenize(tokens: list[int]) -> str:
    return "".join(chr(32 + (t % 95)) for t in tokens[:256])

def embed(text: str) -> list[float]:
    toks = tokenize(text, 32)
    if not toks:
        return [0.0] * 8
    return [round(sum(toks[i::8]) / max(1, len(toks[i::8])) / VOCAB_SIZE, 4) for i in range(8)]
