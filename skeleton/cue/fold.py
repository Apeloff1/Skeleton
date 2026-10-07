"""GB-47 cue fold. Tokens join. Spaced stimulus is dropped."""

from __future__ import annotations


def fold(tokens: list[str]) -> dict:
    clean = [token for token in tokens if token and " " not in token]
    dropped = len(tokens) - len(clean)
    return {
        "kind": "cue-fold",
        "id": ".".join(clean),
        "n": len(clean),
        "dropped": dropped,
        "stored_prose": 0,
    }
