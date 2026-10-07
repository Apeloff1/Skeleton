from __future__ import annotations
"""
Samsung S20 biased shell controls — OOM, thermal, boot, predictive throttle.
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ThermalSample:
    celsius: float
    source: str = "est"
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class S20ShellGuard:
    """
    Targets S20 8GB class devices; 12GB treated as margin.
    """

    def __init__(self, ram_mb: int = 8192, margin_mb: int = 4096):
        self.ram_mb = ram_mb
        self.margin_mb = margin_mb  # extra if 12GB device
        self.budget_mb = int(ram_mb * 0.55)  # stay under 55% for headroom
        self.thermal_limit_c = 42.0
        self.samples: List[ThermalSample] = []
        self.oom_events = 0
        self.throttle_level = 0  # 0..3
        self.boot_stage = "cold"
        self.log: List[dict] = []

    def note_thermal(self, celsius: float, source: str = "est") -> Dict[str, Any]:
        s = ThermalSample(celsius=celsius, source=source)
        self.samples.append(s)
        if len(self.samples) > 200:
            self.samples = self.samples[-200:]
        if celsius >= self.thermal_limit_c + 6:
            self.throttle_level = 3
        elif celsius >= self.thermal_limit_c + 3:
            self.throttle_level = 2
        elif celsius >= self.thermal_limit_c:
            self.throttle_level = 1
        else:
            self.throttle_level = max(0, self.throttle_level - 1)
        return {"throttle_level": self.throttle_level, "celsius": celsius}

    def predictive_throttle(self, work_minutes: float, ambient_c: float = 28.0) -> Dict[str, Any]:
        """Use time as a tool — stretch generative work to avoid heat/OOM."""
        projected = ambient_c + min(18.0, work_minutes * 1.4)
        self.note_thermal(projected, source="predictive")
        slice_sec = 45
        pause_sec = 0
        if self.throttle_level >= 3:
            slice_sec, pause_sec = 15, 40
        elif self.throttle_level == 2:
            slice_sec, pause_sec = 25, 25
        elif self.throttle_level == 1:
            slice_sec, pause_sec = 35, 12
        return {
            "throttle_level": self.throttle_level,
            "work_slice_sec": slice_sec,
            "pause_sec": pause_sec,
            "projected_c": round(projected, 2),
            "advice": "chunk_work" if pause_sec else "continue",
        }

    def memory_guard(self, planned_alloc_mb: float) -> Dict[str, Any]:
        if planned_alloc_mb > self.budget_mb:
            self.oom_events += 1
            return {
                "ok": False,
                "blocked": True,
                "reason": "oom_guard",
                "budget_mb": self.budget_mb,
                "planned_mb": planned_alloc_mb,
            }
        return {"ok": True, "blocked": False, "budget_mb": self.budget_mb}

    def boot_sequence(self) -> List[str]:
        stages = ["cold", "native", "python", "zaibatsu_perimeter", "exocortex", "rooms_cover", "ready"]
        out = []
        for s in stages:
            self.boot_stage = s
            out.append(s)
            self.log.append({"boot": s, "ts": time.time()})
        return out

    def status(self) -> Dict[str, Any]:
        last = self.samples[-1].to_dict() if self.samples else None
        return {
            "ram_mb": self.ram_mb,
            "budget_mb": self.budget_mb,
            "throttle_level": self.throttle_level,
            "oom_events": self.oom_events,
            "boot_stage": self.boot_stage,
            "last_thermal": last,
            "thermal_limit_c": self.thermal_limit_c,
        }
