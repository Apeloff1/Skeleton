"""
Skeleton Resilience — Chaos Engineering Harness

Controlled, surgical failure injection to prove the organism's
recovery machinery works before reality tests it. Every fault the
chaos harness can inject maps to a fault class the RecoveryEngine
already knows how to cure — chaos is the drill, recovery is the fire.

Design:
- FaultInjector: targeted failure injection per subsystem — latency
  spikes, dropped messages, corrupted payloads, handler exceptions,
  sensor freezes, memory pressure simulation, clock skew. Each
  injection is scoped (one subsystem), bounded (auto-expires), and
  reversible (restores exact prior state).
- ChaosSchedule: randomized-but-seeded fault calendar — chaos is
  deterministic given a seed, so any experiment is replayable.
  Intensity ladder from drizzle (1 fault/hr) to monsoon (fault
  bursts with cascading combinations).
- SteadyStateHypothesis: the experiment contract — metrics that must
  hold during chaos (health overall, trust floor, verdict state,
  backlog growth bound). A chaos run passes when the hypothesis
  holds THROUGH the storm and recovery completes after it.
- ExperimentReport: full run record — injections made, hypothesis
  timeline, recovery actions observed, verdict with evidence.

Chaos is always opt-in and always tagged: every injected fault
carries chaos=true so production systems can refuse to participate.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


# ---------------------------------------------------------------------------
# Fault injection primitives
# ---------------------------------------------------------------------------

@dataclass
class Injection:
    """One scoped, bounded, reversible fault injection."""
    injection_id: str
    kind: str
    target: str
    params: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    ttl_s: float = 30.0
    active: bool = True

    def expired(self) -> bool:
        return time.time() - self.started_at > self.ttl_s


INJECTION_KINDS = (
    "latency_spike",     # add N ms to a channel's responses
    "message_drop",      # drop X% of bus events on a topic pattern
    "payload_corrupt",   # flip bytes in payloads on a topic
    "handler_exception", # make a handler raise on next call
    "sensor_freeze",     # hold a sensor channel at its last value
    "memory_pressure",   # simulate memory pressure signal
    "clock_skew",        # offset timestamps by N seconds
)


class FaultInjector:
    """Scoped, bounded, reversible failure injection."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._active: Dict[str, Injection] = {}
        self._restores: Dict[str, Callable[[], None]] = {}
        self._stats = {"injected": 0, "expired": 0, "reverted": 0}

    def inject(self, kind: str, target: str,
               params: Optional[Dict[str, Any]] = None,
               ttl_s: float = 30.0) -> Injection:
        if kind not in INJECTION_KINDS:
            raise ValueError(f"unknown injection kind: {kind}")
        inj = Injection(str(uuid.uuid4())[:8], kind, target, params or {}, ttl_s=ttl_s)
        self._active[inj.injection_id] = inj
        self._stats["injected"] += 1
        if self._bus:
            self._bus.publish(DomainEvent(
                topic="chaos.injection.started",
                payload={"kind": kind, "target": target, "ttl_s": ttl_s, "chaos": True},
            ))
        return inj

    def register_restore(self, injection_id: str, restore: Callable[[], None]) -> None:
        """Register the exact prior-state restorer for an injection."""
        self._restores[injection_id] = restore

    def sweep(self) -> int:
        """Expire due injections and run their restorers. Returns count."""
        reverted = 0
        for inj_id, inj in list(self._active.items()):
            if inj.expired():
                self._revert(inj_id)
                reverted += 1
        return reverted

    def _revert(self, injection_id: str) -> None:
        inj = self._active.pop(injection_id, None)
        if inj is None:
            return
        restore = self._restores.pop(injection_id, None)
        if restore is not None:
            try:
                restore()
            except Exception:
                pass
        inj.active = False
        self._stats["reverted"] += 1
        if self._bus:
            self._bus.emit("chaos.injection.reverted",
                           {"kind": inj.kind, "target": inj.target, "chaos": True})

    def active(self) -> List[Injection]:
        self.sweep()
        return [i for i in self._active.values() if i.active]

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "active": len(self._active)}


# ---------------------------------------------------------------------------
# Chaos scheduling (seeded, replayable)
# ---------------------------------------------------------------------------

@dataclass
class ChaosEvent:
    """One scheduled chaos fault."""
    at_offset_s: float
    kind: str
    target: str
    params: Dict[str, Any]
    ttl_s: float


class ChaosSchedule:
    """Seeded fault calendar — same seed, same storm."""

    INTENSITIES = {
        "drizzle": {"count": 2, "window_s": 3600, "cascade": False},
        "storm": {"count": 6, "window_s": 600, "cascade": False},
        "monsoon": {"count": 12, "window_s": 180, "cascade": True},
    }

    def __init__(self, seed: int = 42):
        self.seed = seed

    def generate(self, intensity: str, targets: List[str]) -> List[ChaosEvent]:
        spec = self.INTENSITIES.get(intensity, self.INTENSITIES["storm"])
        rng = random.Random(self.seed)
        events: List[ChaosEvent] = []
        for i in range(spec["count"]):
            kind = rng.choice(INJECTION_KINDS)
            target = rng.choice(targets)
            events.append(ChaosEvent(
                at_offset_s=rng.uniform(0, spec["window_s"]),
                kind=kind,
                target=target,
                params={"chaos": True, "seed": self.seed, "index": i},
                ttl_s=rng.uniform(10, 60),
            ))
            if spec["cascade"] and rng.random() < 0.4:
                # Cascading combo: a second fault on a related target shortly after
                events.append(ChaosEvent(
                    at_offset_s=events[-1].at_offset_s + rng.uniform(1, 10),
                    kind=rng.choice(INJECTION_KINDS),
                    target=rng.choice(targets),
                    params={"chaos": True, "cascade_from": i},
                    ttl_s=rng.uniform(10, 40),
                ))
        return sorted(events, key=lambda e: e.at_offset_s)


# ---------------------------------------------------------------------------
# Steady-state hypothesis + experiment runner
# ---------------------------------------------------------------------------

@dataclass
class HypothesisCheck:
    """One metric check at one point in the run."""
    metric: str
    expected: str
    observed: Any
    ok: bool
    at_offset_s: float


class SteadyStateHypothesis:
    """The experiment contract: metrics that must hold through chaos."""

    def __init__(self):
        self._checks: List[Callable[[], HypothesisCheck]] = []

    def expect(self, name: str, probe: Callable[[], Any],
               predicate: Callable[[Any], bool], expected: str) -> None:
        """Register: probe() must satisfy predicate() throughout the run."""
        def check() -> HypothesisCheck:
            observed = probe()
            return HypothesisCheck(name, expected, observed, bool(predicate(observed)), 0.0)
        self._checks.append(check)

    def verify(self, at_offset_s: float = 0.0) -> List[HypothesisCheck]:
        out = []
        for c in self._checks:
            h = c()
            h.at_offset_s = at_offset_s
            out.append(h)
        return out


@dataclass
class ExperimentReport:
    """Full chaos run record with verdict and evidence."""
    experiment_id: str
    seed: int
    intensity: str
    injections: int
    checks_total: int
    checks_failed: int
    recovery_actions: int
    passed: bool
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "intensity": self.intensity,
            "injections": self.injections,
            "checks": f"{self.checks_total - self.checks_failed}/{self.checks_total} held",
            "recovery_actions": self.recovery_actions,
            "passed": self.passed,
        }


class ChaosHarness:
    """Runs chaos experiments against the live organism."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self.injector = FaultInjector(bus=bus)
        self._stats = {"experiments": 0, "passed": 0, "failed": 0}

    def run_experiment(self, intensity: str, targets: List[str],
                       hypothesis: SteadyStateHypothesis,
                       recovery: Optional[Any] = None,
                       seed: int = 42,
                       simulate_seconds: bool = True) -> ExperimentReport:
        """Execute a full chaos experiment (time-compressed by default)."""
        self._stats["experiments"] += 1
        schedule = ChaosSchedule(seed).generate(intensity, targets)
        timeline: List[Dict[str, Any]] = []
        checks_total, checks_failed = 0, 0
        recovery_actions = 0

        # Baseline check before the storm
        for h in hypothesis.verify():
            checks_total += 1
            checks_failed += 0 if h.ok else 1
            timeline.append({"phase": "baseline", "metric": h.metric, "ok": h.ok})

        # Storm: inject each scheduled fault (time-compressed)
        injections_made = 0
        for event in schedule:
            self.injector.inject(event.kind, event.target, event.params, event.ttl_s)
            injections_made += 1
            for h in hypothesis.verify(event.at_offset_s):
                checks_total += 1
                checks_failed += 0 if h.ok else 1
            if recovery is not None:
                recovery_actions += len(recovery.cycle())
            timeline.append({"phase": "storm", "kind": event.kind,
                             "target": event.target, "offset": round(event.at_offset_s, 1)})

        # Recovery phase: revert all, verify hypothesis again
        self.injector.sweep()
        for inj in list(self.injector._active):
            self.injector._revert(inj)
        if recovery is not None:
            for _ in range(3):
                recovery_actions += len(recovery.cycle())
        for h in hypothesis.verify():
            checks_total += 1
            checks_failed += 0 if h.ok else 1
            timeline.append({"phase": "recovery", "metric": h.metric, "ok": h.ok})

        passed = checks_failed == 0
        self._stats["passed" if passed else "failed"] += 1
        return ExperimentReport(
            experiment_id=str(uuid.uuid4())[:8],
            seed=seed,
            intensity=intensity,
            injections=injections_made,
            checks_total=checks_total,
            checks_failed=checks_failed,
            recovery_actions=recovery_actions,
            passed=passed,
            timeline=timeline,
        )

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "injector": self.injector.stats()}
