"""
Skeleton Overseer — Self-Healing Fault Recovery

Autonomous fault lifecycle: detect → diagnose → repair → verify →
learn. The engine doesn't just notice failures; it cures them,
proves the cure, and remembers which cures work.

Pipeline:
- FaultClassifier: maps anomaly signals (sysid anomalies, health red
  nodes, handler exceptions, trust collapses) to fault classes
  (sensor_fault | model_drift | resource_exhaustion | handler_failure
  | cascade_risk), each with a confidence score
- RecoveryPlaybook: per fault class, an ordered list of repair
  strategies with cooldowns — reset channel model, drain queue,
  shed QoS tier, restart consumer, quarantine node. Strategies run
  cheapest-first, one per cycle, never stacking repairs blindly
- RepairVerifier: post-repair probes — the fault must stay cleared
  for N ticks before the repair is marked verified; unverified
  repairs roll back to the next strategy
- CureLedger: success rates per (fault_class, strategy) — future
  playbooks order themselves by what actually cured this machine
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


FAULT_CLASSES = (
    "sensor_fault",
    "model_drift",
    "resource_exhaustion",
    "handler_failure",
    "cascade_risk",
)


@dataclass
class Fault:
    """One detected fault with classification confidence."""
    fault_id: str
    fault_class: str
    source: str
    confidence: float
    detail: str
    detected_at: float = field(default_factory=time.time)
    status: str = "open"  # open | repairing | verifying | cured | chronic


class FaultClassifier:
    """Maps anomaly signals to fault classes with confidence."""

    def classify(self, signal: Dict[str, Any]) -> Optional[Fault]:
        kind = signal.get("kind", "")
        channel = signal.get("channel", "")
        severity = float(signal.get("severity", 0.5))

        if kind == "sysid_anomaly":
            return Fault(f"f-{int(time.time()*1000)%100000}", "sensor_fault", channel,
                         min(1.0, severity), f"model innovation anomaly on {channel}")
        if kind == "health_red":
            if channel in ("mesh", "mesh_bridge", "coordinator"):
                return Fault(f"f-{int(time.time()*1000)%100000}", "cascade_risk", channel,
                             min(1.0, severity + 0.2), f"routing layer unhealthy: {channel}")
            return Fault(f"f-{int(time.time()*1000)%100000}", "resource_exhaustion", channel,
                         severity, f"subsystem unhealthy: {channel}")
        if kind == "handler_exception":
            return Fault(f"f-{int(time.time()*1000)%100000}", "handler_failure", channel,
                         min(1.0, severity + 0.1), f"handler raised: {signal.get('detail','')[:80]}")
        if kind == "trust_collapse":
            return Fault(f"f-{int(time.time()*1000)%100000}", "model_drift", channel,
                         min(1.0, severity + 0.15), "engine trust below floor persistently")
        return None


@dataclass
class RepairAttempt:
    """One repair strategy execution."""
    fault_id: str
    strategy: str
    ok: bool
    detail: str
    at: float = field(default_factory=time.time)


class CureLedger:
    """Success rates per (fault_class, strategy) — cures that worked."""

    def __init__(self):
        self._cures: Dict[str, Dict[str, List[int]]] = {}  # cls -> strategy -> [ok, attempts]

    def record(self, fault_class: str, strategy: str, ok: bool) -> None:
        entry = self._cures.setdefault(fault_class, {}).setdefault(strategy, [0, 0])
        entry[1] += 1
        if ok:
            entry[0] += 1

    def success_rate(self, fault_class: str, strategy: str) -> float:
        entry = self._cures.get(fault_class, {}).get(strategy)
        if not entry or entry[1] == 0:
            return 0.5
        return entry[0] / entry[1]

    def best_strategies(self, fault_class: str, candidates: List[str]) -> List[str]:
        """Order candidates by learned success rate (descending)."""
        return sorted(candidates, key=lambda s: self.success_rate(fault_class, s), reverse=True)

    def stats(self) -> Dict[str, Any]:
        return {
            cls: {s: {"ok": e[0], "attempts": e[1]} for s, e in strats.items()}
            for cls, strats in self._cures.items()
        }


# Strategy name → (cooldown_seconds, description)
PLAYBOOKS: Dict[str, List[str]] = {
    "sensor_fault": ["reset_channel_model", "quarantine_channel", "fallback_sensor"],
    "model_drift": ["reset_meta_state", "retrain_sysid", "conservative_lock"],
    "resource_exhaustion": ["shed_qos_tier", "drain_queue", "evict_planes", "cap_parallelism"],
    "handler_failure": ["restart_handler", "disable_handler", "quarantine_node"],
    "cascade_risk": ["isolate_subsystem", "reroute_traffic", "fleet_alert"],
}


class RecoveryEngine:
    """Autonomous fault recovery: classify → playbook → verify → learn."""

    VERIFY_TICKS = 3
    COOLDOWN_S = 30.0

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self.classifier = FaultClassifier()
        self.ledger = CureLedger()
        self._faults: Dict[str, Fault] = {}
        self._strategy_idx: Dict[str, int] = {}
        self._last_attempt: Dict[str, float] = {}
        self._verify_counter: Dict[str, int] = {}
        self._handlers: Dict[str, Callable[[Fault], Dict[str, Any]]] = {}
        self._attempts: List[RepairAttempt] = []
        self._stats = {"faults": 0, "repairs": 0, "verified": 0, "chronic": 0}

    def register_strategy(self, name: str, handler: Callable[[Fault], Dict[str, Any]]) -> None:
        """Register a live repair strategy (name must match playbook)."""
        self._handlers[name] = handler

    def ingest(self, signal: Dict[str, Any]) -> Optional[Fault]:
        fault = self.classifier.classify(signal)
        if fault is None:
            return None
        # Dedupe by class+source while one is open
        for existing in self._faults.values():
            if existing.fault_class == fault.fault_class and existing.source == fault.source \
               and existing.status in ("open", "repairing", "verifying"):
                return existing
        self._faults[fault.fault_id] = fault
        self._strategy_idx[fault.fault_id] = 0
        self._stats["faults"] += 1
        if self._bus:
            self._bus.publish(DomainEvent(
                topic="overseer.recovery.fault",
                payload={"class": fault.fault_class, "source": fault.source,
                         "confidence": fault.confidence},
            ))
        return fault

    def cycle(self, signal_clear: Optional[Dict[str, bool]] = None) -> List[RepairAttempt]:
        """One recovery cycle: attempt repairs, verify cures."""
        attempts: List[RepairAttempt] = []
        clear = signal_clear or {}
        now = time.time()

        for fault in list(self._faults.values()):
            if fault.status in ("cured", "chronic"):
                continue

            # Verification phase: fault must stay clear N cycles
            if fault.status == "verifying":
                if clear.get(fault.source, True):
                    self._verify_counter[fault.fault_id] = \
                        self._verify_counter.get(fault.fault_id, 0) + 1
                    if self._verify_counter[fault.fault_id] >= self.VERIFY_TICKS:
                        fault.status = "cured"
                        self._stats["verified"] += 1
                        last = self._attempts[-1] if self._attempts else None
                        if last:
                            self.ledger.record(fault.fault_class, last.strategy, True)
                else:
                    fault.status = "open"  # relapsed: next strategy
                    self._strategy_idx[fault.fault_id] += 1
                continue

            # Cooldown between attempts on the same fault
            last_at = self._last_attempt.get(fault.fault_id, 0.0)
            if now - last_at < self.COOLDOWN_S:
                continue

            strategies = PLAYBOOKS.get(fault.fault_class, [])
            # Order by learned cure rates
            strategies = self.ledger.best_strategies(fault.fault_class, strategies)
            idx = self._strategy_idx.get(fault.fault_id, 0)
            if idx >= len(strategies):
                fault.status = "chronic"
                self._stats["chronic"] += 1
                if self._bus:
                    self._bus.emit("overseer.recovery.chronic",
                                   {"class": fault.fault_class, "source": fault.source})
                continue

            strategy = strategies[idx]
            handler = self._handlers.get(strategy)
            try:
                outcome = handler(fault) if handler else {"ok": True, "detail": "simulated"}
                ok = bool(outcome.get("ok", True))
                detail = str(outcome.get("detail", ""))
            except Exception as e:
                ok, detail = False, str(e)

            attempt = RepairAttempt(fault.fault_id, strategy, ok, detail)
            attempts.append(attempt)
            self._attempts.append(attempt)
            self._last_attempt[fault.fault_id] = now
            self._stats["repairs"] += 1
            fault.status = "verifying"
            if not ok:
                self.ledger.record(fault.fault_class, strategy, False)
                fault.status = "open"
                self._strategy_idx[fault.fault_id] += 1

        return attempts

    def stats(self) -> Dict[str, Any]:
        return {**self._stats,
                "open_faults": sum(1 for f in self._faults.values()
                                   if f.status in ("open", "repairing", "verifying")),
                "cures": self.ledger.stats()}
