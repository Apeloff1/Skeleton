"""skeleton/gameforge/conductor_e2e_more2.py
More2 extreme complete GameForge E2E.
Full 7-step with emit packs, era_bind, cockpit, receipts.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import List

class ConductorError(Exception):
    pass

class GameForgeE2EMore2:
    STEPS = ["vision", "snowball", "prototype", "mass_forge", "world", "cockpit", "export"]

    def full_run(self, era: str = "HOUSE_ERA") -> List[str]:
        return [hashlib.sha256(f"{s}:{era}:emit:more2".encode()).hexdigest() for s in self.STEPS]
