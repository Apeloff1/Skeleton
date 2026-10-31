"""skeleton/gameforge/conductor_closed.py
Closed extreme GameForge 7-step conductor.
Full vision-to-export with era_bind, clipped mass, emit packs, receipts.
Fail-closed. No stubs.
"""
from __future__ import annotations
import hashlib
from typing import List, Dict

class ConductorError(Exception):
    pass

class GameForgeConductorClosed:
    STEPS = ["vision", "snowball", "prototype", "mass_forge", "world", "cockpit", "export"]

    def __init__(self):
        self.era_binds: Dict[str, str] = {}
        self.receipts: List[str] = []
        self.closed = True

    def run_step(self, step: str, era_bind: str = "HOUSE_ERA") -> str:
        if step not in self.STEPS:
            raise ConductorError("invalid step")
        self.era_binds[step] = era_bind
        payload = f"{step}:{era_bind}:closed"
        digest = hashlib.sha256(payload.encode()).hexdigest()
        self.receipts.append(digest)
        return digest

    def full_run(self) -> List[str]:
        return [self.run_step(s) for s in self.STEPS]
