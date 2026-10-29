"""Dialogue selector.
Selects lines from optical, salvage, boss phase, and ending state.
"""
from typing import Any, Dict, List

class DialogueSelector:
    LINES = {
        "intro": "The ash tunnels open.",
        "high_opt": "Optical density is high.",
        "rich": "Salvage is abundant.",
        "boss_near": "The core is close.",
        "extract": "Extract is ready.",
    }

    def select(self, optical: float, salvage: int, boss_phase: int, ending: str) -> List[str]:
        out = ["intro"]
        if optical > 0.9:
            out.append("high_opt")
        if salvage > 30:
            out.append("rich")
        if boss_phase >= 3:
            out.append("boss_near")
        if ending in ("extract_rich", "extract"):
            out.append("extract")
        return [self.LINES[k] for k in out]

    def status(self) -> Dict[str, Any]:
        return {"available": list(self.LINES), "schema": "skeleton.dialogue.v1"}
