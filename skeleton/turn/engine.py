"""Headless play loop. extract / heat / sleep. Warp extracts once."""

from __future__ import annotations

from skeleton.turn.law import TICKS


class TurnEngine:
    def __init__(self) -> None:
        self.tick = 0
        self.extract_count = 0
        self.warp_count = 0
        self.heat = 0.0
        self.phase = "sleep"
        self.warped = False

    def extract(self) -> str:
        if not self.warped:
            self.warped = True
            self.warp_count += 1
            self.extract_count += 1
            self.phase = "extract"
        return self.phase

    def heat_step(self) -> str:
        self.heat = min(1.0, self.heat + 0.05)
        self.phase = "heat"
        return self.phase

    def sleep(self) -> str:
        self.phase = "dream" if self.heat >= 0.2 else "sleep"
        self.heat = max(0.0, self.heat - 0.03)
        return self.phase

    def step(self) -> str:
        self.tick += 1
        if self.tick == 1:
            return self.extract()
        if self.tick % 3 == 0:
            return self.sleep()
        return self.heat_step()

    def run(self, n: int = TICKS) -> dict:
        last = "sleep"
        for _ in range(n):
            last = self.step()
        return {
            "kind": "turn",
            "ticks": self.tick,
            "extract_count": self.extract_count,
            "warp_count": self.warp_count,
            "phase": last,
            "stored_prose": 0,
        }
