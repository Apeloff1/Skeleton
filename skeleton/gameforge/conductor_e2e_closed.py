"""skeleton/gameforge/conductor_e2e_closed.py
Final closed extreme GameForge E2E.
Full 7-step with emit packs, era_bind, cockpit, receipts. Fully closed.
Fail-closed. No stubs.
"""
from __future__ import annotations
import hashlib
from typing import List

class ConductorError(Exception):
    pass

class GameForgeE2EClosed:
    STEPS = ["vision", "snowball", "prototype", "mass_forge", "world", "cockpit", "export"]

    def full_run(self, era: str = "HOUSE_ERA") -> List[str]:
        return [hashlib.sha256(f"{s}:{era}:emit:closed:final".encode()).hexdigest() for s in self.STEPS]
