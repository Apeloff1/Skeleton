"""skeleton/router/unify_100x.py
100x extreme complete router contract.
Single routing between EconomicOptimiser and cascade. No third router.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class RouterError(Exception):
    pass

class RouterUnify100x:
    def route(self, gate: str) -> str:
        if gate not in ("economic", "cascade"):
            raise RouterError("invalid gate")
        return hashlib.sha256(f"route:{gate}".encode()).hexdigest()
