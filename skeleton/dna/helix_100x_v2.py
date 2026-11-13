"""skeleton/dna/helix_100x_v2.py
Further 100x extreme DNAHelix / genos organ.
Pair emission, genos coil pulse, persist under chronicle.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import List, Tuple

class HelixError(Exception):
    pass

class DNAHelix100xV2:
    def emit_pair(self, a: str, b: str) -> Tuple[str, str]:
        if not a or not b:
            raise HelixError("empty")
        return hashlib.sha256(a.encode()).hexdigest(), hashlib.sha256(b.encode()).hexdigest()

    def pulse(self, pairs: List[Tuple[str, str]]) -> str:
        payload = ":".join(f"{p[0][:8]}{p[1][:8]}" for p in pairs)
        return hashlib.sha256(payload.encode()).hexdigest()
