"""Pack C telemetry — snapshots compatible with cortex control surfaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple
import time


@dataclass
class PackSnapshot:
    name: str
    version: str
    counters: Dict[str, int] = field(default_factory=dict)
    gauges: Dict[str, float] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "labels": dict(self.labels),
            "ts": self.ts,
        }


@dataclass
class CortexPackTelemetry:
    name: str = "pack_c"
    version: str = "2026.09.20"
    _counters: Dict[str, int] = field(default_factory=dict)
    _gauges: Dict[str, float] = field(default_factory=dict)
    _labels: Dict[str, str] = field(default_factory=dict)
    history: List[PackSnapshot] = field(default_factory=list)

    def inc(self, key: str, n: int = 1) -> None:
        self._counters[key] = self._counters.get(key, 0) + n

    def set_gauge(self, key: str, value: float) -> None:
        self._gauges[key] = float(value)

    def label(self, key: str, value: str) -> None:
        self._labels[key] = value

    def mark_pfc_lock(self) -> None:
        self.label("pfc.attn", "false")
        self.inc("pfc.lock.asserts")

    def mark_amalgam(self, kind: str) -> None:
        self.inc(f"amalgam.kind.{kind}")
        if kind == "own":
            self.inc("amalgam.unfitted")
        elif kind == "own-lm":
            self.inc("amalgam.fitted")

    def snapshot(self) -> PackSnapshot:
        snap = PackSnapshot(
            name=self.name,
            version=self.version,
            counters=dict(self._counters),
            gauges=dict(self._gauges),
            labels=dict(self._labels),
        )
        self.history.append(snap)
        if len(self.history) > 256:
            self.history = self.history[-256:]
        return snap


TELEMETRY_KEYS: Tuple[str, ...] = tuple(
    f"metric.{family}.{i:03d}"
    for family in ("router", "amalgam", "ledger", "moe", "persist", "queue", "depth", "sigil")
    for i in range(1, 81)
)


def warm_telemetry() -> CortexPackTelemetry:
    tel = CortexPackTelemetry()
    tel.mark_pfc_lock()
    for i, key in enumerate(TELEMETRY_KEYS):
        if i % 2 == 0:
            tel.inc(key, (i % 5) + 1)
        else:
            tel.set_gauge(key, (i % 97) / 97.0)
    return tel
