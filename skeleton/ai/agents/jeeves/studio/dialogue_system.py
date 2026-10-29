"""Dialogue system.
Branching lines driven by optical, salvage, and quest state.
"""
from __future__ import annotations
from typing import Any, Dict, List

LINES = [
    {"id": "intro", "text": "The ash settles. You move.", "cond": "always"},
    {"id": "high_opt", "text": "The tunnels brighten. Patterns emerge.", "cond": "optical>0.9"},
    {"id": "rich", "text": "Salvage glows in your pack.", "cond": "salvage>30"},
    {"id": "boss_near", "text": "Something large waits ahead.", "cond": "boss_phase>=1"},
    {"id": "quest_done", "text": "An objective clears.", "cond": "quests>0"},
    {"id": "ending_extract", "text": "You choose to leave.", "cond": "ending==extract"},
    {"id": "ending_remain", "text": "You stay in the dark.", "cond": "ending==remain"},
]

class DialogueSystem:
    def select(self, optical: float, salvage: int, boss_phase: int, quests_done: int, ending: str = "") -> List[Dict[str, Any]]:
        out = []
        for line in LINES:
            c = line["cond"]
            if c == "always":
                out.append(line)
            elif c == "optical>0.9" and optical > 0.9:
                out.append(line)
            elif c == "salvage>30" and salvage > 30:
                out.append(line)
            elif c == "boss_phase>=1" and boss_phase >= 1:
                out.append(line)
            elif c == "quests>0" and quests_done > 0:
                out.append(line)
            elif c == "ending==extract" and ending == "extract":
                out.append(line)
            elif c == "ending==remain" and ending == "remain":
                out.append(line)
        return out
