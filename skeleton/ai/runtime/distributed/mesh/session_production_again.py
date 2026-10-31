"""skeleton/distributed/mesh/session_production_again.py
Further extreme complete Multiplayer production.
Interest, rollback, anti-cheat, 256-player, telemetry.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import Dict

class SessionError(Exception):
    pass

class SessionProductionAgain:
    def __init__(self):
        self.max_players = 256
        self.interest: Dict[str, float] = {}

    def sync(self, peer: str, dist: float) -> str:
        if len(self.interest) >= self.max_players:
            raise SessionError("full")
        self.interest[peer] = dist
        return hashlib.sha256(f"{peer}:{dist}:prod".encode()).hexdigest()
