"""Dense narrative sequences.
Multi-act branches, optical/economy triggers, ending variants, camera cues.
"""
from __future__ import annotations
from typing import Any, Dict, List

SEQUENCES = [
    {"id": "seq_0", "act": 1, "branch": "standard", "prompt": "Tunnels shift on standard", "duration": 5.0, "camera": [0, 0], "optical_min": 0.70},
    {"id": "seq_1", "act": 1, "branch": "high_optical", "prompt": "Tunnels shift on high_optical", "duration": 6.0, "camera": [1, 1], "optical_min": 0.75},
    {"id": "seq_2", "act": 1, "branch": "wealthy", "prompt": "Tunnels shift on wealthy", "duration": 7.0, "camera": [2, 2], "optical_min": 0.80},
    {"id": "seq_3", "act": 1, "branch": "low_salvage", "prompt": "Tunnels shift on low_salvage", "duration": 8.0, "camera": [3, 3], "optical_min": 0.85},
    {"id": "seq_4", "act": 2, "branch": "standard", "prompt": "Tunnels shift on standard", "duration": 5.0, "camera": [4, 4], "optical_min": 0.70},
    {"id": "seq_5", "act": 2, "branch": "high_optical", "prompt": "Tunnels shift on high_optical", "duration": 6.0, "camera": [5, 5], "optical_min": 0.75},
    {"id": "seq_6", "act": 2, "branch": "wealthy", "prompt": "Tunnels shift on wealthy", "duration": 7.0, "camera": [6, 0], "optical_min": 0.80},
    {"id": "seq_7", "act": 2, "branch": "low_salvage", "prompt": "Tunnels shift on low_salvage", "duration": 8.0, "camera": [7, 1], "optical_min": 0.85},
]

class NarrativeEngine:
    def __init__(self):
        self.history = []
    def next_act(self, optical: float, salvage: int) -> Dict[str, Any]:
        for seq in SEQUENCES:
            if optical >= seq["optical_min"] and (seq["branch"] != "wealthy" or salvage > 25):
                self.history.append(seq["id"])
                return seq
        return SEQUENCES[0]
    def ending(self, salvage: int, optical: float) -> str:
        if salvage > 40 and optical > 0.9:
            return "extract_rich"
        if salvage > 25:
            return "extract"
        return "remain"
