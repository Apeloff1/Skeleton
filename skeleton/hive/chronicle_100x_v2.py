"""skeleton/hive/chronicle_100x_v2.py
Further 100x extreme Hive merkle gossip + chronicle.
Root history, tournament on roots, local helix jsonl consensus. No chain, no coin.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import List

class ChronicleError(Exception):
    pass

class HiveChronicle100xV2:
    def __init__(self):
        self.roots: List[str] = []
        self.helix: List[dict] = []

    def gossip_root(self, root: str) -> str:
        if len(root) != 64:
            raise ChronicleError("invalid root")
        self.roots.append(root)
        return hashlib.sha256(root.encode()).hexdigest()

    def tournament(self) -> str:
        if not self.roots:
            raise ChronicleError("empty")
        winner = hashlib.sha256(":".join(self.roots[-16:]).encode()).hexdigest()
        self.helix.append({"winner": winner, "count": len(self.roots)})
        return winner
