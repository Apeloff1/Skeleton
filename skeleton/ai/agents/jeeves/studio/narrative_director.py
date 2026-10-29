"""Narrative and cutscene subsystem (10x).
Sequenced acts, camera moves, optical cues, ending branches.
"""
from __future__ import annotations
from typing import Any, Dict, List

CUTSCENES = [
    {"id": "act_0", "prompt": "Sequence 0: ash tunnels phase", "duration": 4.0, "camera": [0, 0], "optical": "tile_0", "branch": 0},
    {"id": "act_1", "prompt": "Sequence 1: ash tunnels phase", "duration": 5.0, "camera": [1, 1], "optical": "tile_1", "branch": 1},
    {"id": "act_2", "prompt": "Sequence 2: ash tunnels phase", "duration": 6.0, "camera": [2, 2], "optical": "tile_2", "branch": 2},
    {"id": "act_3", "prompt": "Sequence 3: ash tunnels phase", "duration": 7.0, "camera": [3, 3], "optical": "tile_3", "branch": 0},
    {"id": "act_4", "prompt": "Sequence 4: ash tunnels phase", "duration": 8.0, "camera": [4, 4], "optical": "tile_4", "branch": 1},
]

class CutsceneDirector:
    def __init__(self):
        self.current = 0
        self.timer = 0.0
        self.finished = False
        self.sequence: List[Dict[str, Any]] = []
    def play(self, sequence: List[Dict[str, Any]] = None) -> None:
        self.sequence = sequence or CUTSCENES
        self.current = 0
        self.timer = 0.0
        self.finished = False
    def update(self, dt: float) -> Dict[str, Any]:
        if self.finished or self.current >= len(self.sequence):
            self.finished = True
            return {"finished": True, "act": self.current}
        self.timer += dt
        act = self.sequence[self.current]
        if self.timer >= act["duration"]:
            self.timer = 0.0
            self.current += 1
        return {"act": self.current, "timer": self.timer, "finished": False, "prompt": act.get("prompt")}
