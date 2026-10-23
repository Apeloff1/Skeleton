"""skeleton/hive/chronicle_closed.py
Closed extreme Hive merkle gossip + chronicle.
Root history, tournament, helix consensus. No chain, no coin.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import List

class ChronicleError(Exception):
    pass

class HiveChronicleClosed:
    def __init__(self):
        self.roots: List[str] = []
        self.helix: List[dict] = []
        self.closed = True

    def gossip_root(self, root: str) -> str:
        if len(root) != 64:
            raise ChronicleError("invalid root")
        self.roots.append(root)
        return hashlib.sha256(root.encode()).hexdigest()

    def tournament(self) -> str:
        if not self.roots:
            raise ChronicleError("empty")
        winner = hashlib.sha256(":".join(self.roots).encode()).hexdigest()
        self.helix.append({"winner": winner, "count": len(self.roots), "closed": True})
        return winner
