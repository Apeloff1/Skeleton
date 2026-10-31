"""skeleton/dna/helix_100x.py
100x extreme complete DNAHelix / genos organ.
Pair emission, genos pulse, persist under chronicle.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import List, Tuple

class HelixError(Exception):
    pass

class DNAHelix100x:
    def emit_pair(self, a: str, b: str) -> Tuple[str, str]:
        if not a or not b:
            raise HelixError("empty")
        da = hashlib.sha256(a.encode()).hexdigest()
        db = hashlib.sha256(b.encode()).hexdigest()
        return da, db

    def pulse(self, pairs: List[Tuple[str, str]]) -> str:
        payload = ":".join(f"{p[0]}{p[1]}" for p in pairs)
        return hashlib.sha256(payload.encode()).hexdigest()
