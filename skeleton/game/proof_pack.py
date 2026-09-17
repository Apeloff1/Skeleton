"""Named proofs. Pointer only."""

from __future__ import annotations

from typing import Any


class ProofPackError(ValueError):
    pass


PROOF = tuple(f"pf_{i:02d}" for i in range(16))


def pull(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in PROOF:
        raise ProofPackError(name)
    if not digest:
        raise ProofPackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("proof") or {})
    cur[name] = digest
    nxt["proof"] = cur
    nxt["stored_prose"] = 0
    return nxt
