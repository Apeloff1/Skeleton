"""Headless render loop.
Samples optical and updates chunks each tick.
"""
from typing import Any, Dict, List

class HeadlessRenderLoop:
    def __init__(self):
        self.ticks = 0
        self.chunks: Dict[str, float] = {}

    def tick(self, optical: float, x: int, y: int) -> Dict[str, Any]:
        self.ticks += 1
        cid = f"{x // 16}_{y // 16}"
        self.chunks[cid] = optical
        return {
            "tick": self.ticks,
            "chunk": cid,
            "optical": optical,
            "schema": "skeleton.headless.render.v1",
        }
