"""RAM arena — buddy + slab + clock + balloon as one device."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ram.balloon import Balloon
from skeleton.kernel.ram.buddy import Buddy
from skeleton.kernel.ram.clock import Clock
from skeleton.kernel.ram.slab import Slab


class Arena:
    def __init__(self, *, mobile: bool = True) -> None:
        self.buddy = Buddy(orders=6 if mobile else 8, root=10 if mobile else 12)
        self.slab = Slab(width=4 if mobile else 8, limit=8 if mobile else 24)
        self.clock = Clock(frames=16 if mobile else 64)
        self.balloon = Balloon()
        self.puts = 0

    def put(self, key: str, need: int = 16) -> Dict[str, Any]:
        addr = self.buddy.alloc(need)
        slot = self.slab.put(key)
        frame = self.clock.touch(key)
        self.puts += 1
        return {"addr": addr, "slot": slot, "frame": frame}

    def pressure(self, p: float) -> Dict[str, Any]:
        killed = 0
        if p >= 0.82:
            killed = self.balloon.inflate(self.clock, fraction=0.35)
        elif p >= 0.62:
            killed = self.balloon.inflate(self.clock, fraction=0.15)
        return {"killed": killed, "pressure": p}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-ram",
            "puts": self.puts,
            "buddy": self.buddy.card(),
            "slab": self.slab.card(),
            "clock": self.clock.card(),
            "balloon": self.balloon.card(),
            "stored_prose": 0,
        }
