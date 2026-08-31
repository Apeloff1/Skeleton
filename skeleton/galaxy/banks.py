"""Hierarchical memory banks — common vs long-tail.

Frequency split on token occurrence across the mesh. Common tokens
form a residual block (hashed unit floats) that a mouth may ingest
if it exposes ingest_residual. Long-tail stays on the wiki shelf.
No production KV cache is claimed.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Dict, List, Tuple


def _hash_unit(token: str) -> float:
    raw = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(raw[:2], "big") / 65535.0


def split(mesh) -> Tuple[List[str], List[str]]:
    counts: Counter = Counter()
    for lib in (*mesh.brains.values(), mesh.wiki):
        for atom in lib.all():
            if atom.superseded_by:
                continue
            counts.update(atom.tokens)
    if not counts:
        return [], []
    freqs = sorted(counts.values())
    median = freqs[len(freqs) // 2]
    common = sorted(t for t, n in counts.items() if n >= max(2, median))
    tail = sorted(t for t, n in counts.items() if n < max(2, median))
    return common, tail


def residual_block(common: List[str], *, n: int = 16) -> List[float]:
    return [_hash_unit(t) for t in common[:n]]


def card(mesh, *, neo: Any = None) -> Dict[str, Any]:
    common, tail = split(mesh)
    block = residual_block(common)
    ingested = 0
    if neo is not None and hasattr(neo, "ingest_residual") and block:
        try:
            neo.ingest_residual(block)
            ingested = 1
        except Exception:
            ingested = 0
    return {
        "kind": "memory-banks",
        "common": common[:32],
        "longtail": tail[:32],
        "common_n": len(common),
        "longtail_n": len(tail),
        "residual": [round(x, 4) for x in block],
        "ingested": ingested,
        "stored_prose": 0,
    }
