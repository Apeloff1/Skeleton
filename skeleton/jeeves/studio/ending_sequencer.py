"""Ending sequencer.
Selects and sequences final cutscene from salvage, optical, reputation, and boss state.
"""
from __future__ import annotations
from typing import Any, Dict, List

class EndingSequencer:
    def select(self, salvage: int, optical: float, reputation: int, boss_defeated: bool) -> Dict[str, Any]:
        if not boss_defeated:
            return {"id": "failure", "title": "The tunnels close", "acts": 2}
        if salvage > 50 and optical > 0.95 and reputation > 20:
            return {"id": "legend", "title": "Ash legend", "acts": 5}
        if salvage > 30 and optical > 0.9:
            return {"id": "extract_rich", "title": "Rich extract", "acts": 4}
        if salvage > 15:
            return {"id": "extract", "title": "Extract", "acts": 3}
        return {"id": "remain", "title": "Remain", "acts": 3}
    def sequence(self, ending_id: str) -> List[str]:
        base = ["fade_in", "final_dialogue", "credits"]
        if ending_id == "legend":
            return ["optical_peak", "faction_tribute"] + base
        if ending_id == "extract_rich":
            return ["salvage_glow"] + base
        return base
