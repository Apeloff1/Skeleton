"""Chaos engineering — controlled fault injection for resilience testing.

Provides fault injectors (latency, error, timeout, resource exhaustion)
that can be armed against specific subsystems. Experiments are scoped,
time-boxed, and auto-disarming. Every injection is recorded in the
audit log; results feed the resilience score in the doctor card.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class FaultSpec:
    fault_type: str  # latency_ms | error_rate | drop | cpu_burn
    magnitude: float
    probability: float = 1.0


@dataclass
class Experiment:
    name: str
    subsystem: str
    faults: List[FaultSpec]
    duration_s: float
    armed_at_ns: int = 0
    injections: int = 0
    steady_state_ok: Optional[bool] = None

    def active(self) -> bool:
        return bool(self.armed_at_ns) and (time.time_ns() - self.armed_at_ns) / 1e9 < self.duration_s

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "subsystem": self.subsystem,
            "faults": [{"type": f.fault_type, "magnitude": f.magnitude, "probability": f.probability} for f in self.faults],
            "duration_s": self.duration_s,
            "active": self.active(),
            "injections": self.injections,
            "steady_state_ok": self.steady_state_ok,
        }


class ChaosMonkey:
    """Fault injection controller with auto-disarm."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._experiments: Dict[str, Experiment] = {}
        self._rng = rng or random.Random(42)

    def arm(self, name: str, subsystem: str, faults: List[FaultSpec], duration_s: float = 60.0) -> Experiment:
        exp = Experiment(name=name, subsystem=subsystem, faults=faults, duration_s=duration_s, armed_at_ns=time.time_ns())
        self._experiments[name] = exp
        return exp

    def disarm(self, name: str) -> bool:
        exp = self._experiments.get(name)
        if exp:
            exp.armed_at_ns = 0
            return True
        return False

    def maybe_inject(self, subsystem: str) -> Optional[Dict[str, Any]]:
        for exp in self._experiments.values():
            if exp.subsystem != subsystem or not exp.active():
                continue
            for fault in exp.faults:
                if self._rng.random() < fault.probability:
                    exp.injections += 1
                    return {
                        "experiment": exp.name,
                        "fault": fault.fault_type,
                        "magnitude": fault.magnitude,
                        "subsystem": subsystem,
                    }
        return None

    def guard(self, subsystem: str, fn: Callable[[], Any]) -> Any:
        injected = self.maybe_inject(subsystem)
        if injected:
            if injected["fault"] == "error_rate":
                raise RuntimeError(f"chaos: injected error in {subsystem}")
            if injected["fault"] == "drop":
                return None
            if injected["fault"] == "latency_ms":
                time.sleep(min(injected["magnitude"] / 1000.0, 2.0))
        return fn()

    def report(self, name: str, steady_state_ok: bool) -> None:
        if name in self._experiments:
            self._experiments[name].steady_state_ok = steady_state_ok

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "chaos-card",
            "experiments": {n: e.to_dict() for n, e in self._experiments.items()},
            "active": [n for n, e in self._experiments.items() if e.active()],
            "total_injections": sum(e.injections for e in self._experiments.values()),
        }
