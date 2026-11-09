"""Quorum sensing for the swarm.

Bacterial colonies don't act on a single cell's signal — they act when
the *density* of signalling crosses a threshold, turning a noisy mob
into a coordinated organism. The swarm gets the same trick: agents emit
signals ("I see load", "I found prey", "I'm failing") and the quorum
sensor decides when enough of the colony agrees to flip a collective
behaviour on or off.

Key properties:

- signals carry TTLs — a stale vote decays out of the count, so the
  quorum reflects the colony *now*, not last hour,
- per-behaviour thresholds expressed as a fraction of the active
  population (or an absolute count for small swarms),
- hysteresis: engage and release thresholds differ, so behaviours
  don't flicker at the boundary,
- pure and synchronous; the mesh feeds it signals, behaviours subscribe.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from ..kernel.errors import SkeletonError


class QuorumError(SkeletonError):
    code = "SWM.QUORUM"


class CollectiveState(str, Enum):
    DORMANT = "dormant"
    ENGAGED = "engaged"


@dataclass(frozen=True)
class Signal:
    agent_id: str
    behaviour: str
    emitted_at: float
    ttl_s: float
    weight: float = 1.0

    def alive(self, now: float) -> bool:
        return now - self.emitted_at < self.ttl_s


@dataclass
class BehaviourGate:
    """One collective behaviour guarded by a quorum threshold."""

    name: str
    engage_fraction: float = 0.5      # fraction of active population to engage
    release_fraction: float = 0.3     # drop below this to release (hysteresis)
    absolute_floor: int = 1           # minimum raw count regardless of fraction
    state: CollectiveState = CollectiveState.DORMANT
    engaged_at: Optional[float] = None
    transitions: int = 0


class QuorumSensor:
    """Counts live signals per behaviour and flips collective gates."""

    def __init__(self, population_probe: Optional[Callable[[], int]] = None) -> None:
        self._signals: Dict[str, List[Signal]] = {}
        self._gates: Dict[str, BehaviourGate] = {}
        self._population_probe = population_probe or (lambda: 0)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_behaviour(
        self,
        name: str,
        *,
        engage_fraction: float = 0.5,
        release_fraction: float = 0.3,
        absolute_floor: int = 1,
    ) -> BehaviourGate:
        if not 0.0 < release_fraction <= engage_fraction <= 1.0:
            raise QuorumError(
                "thresholds must satisfy 0 < release <= engage <= 1",
                context={"engage": engage_fraction, "release": release_fraction},
            )
        gate = BehaviourGate(
            name=name,
            engage_fraction=engage_fraction,
            release_fraction=release_fraction,
            absolute_floor=absolute_floor,
        )
        self._gates[name] = gate
        self._signals.setdefault(name, [])
        return gate

    # ------------------------------------------------------------------
    # Signalling
    # ------------------------------------------------------------------

    def emit(self, agent_id: str, behaviour: str, *, ttl_s: float = 60.0,
             weight: float = 1.0, now: Optional[float] = None) -> Signal:
        if behaviour not in self._gates:
            raise QuorumError(
                "signal for unregistered behaviour",
                context={"behaviour": behaviour, "agent_id": agent_id},
            )
        now = time.time() if now is None else now
        signal = Signal(agent_id=agent_id, behaviour=behaviour,
                        emitted_at=now, ttl_s=ttl_s, weight=weight)
        bucket = self._signals[behaviour]
        # one live vote per agent — replace any prior signal from this agent
        bucket[:] = [s for s in bucket if s.agent_id != agent_id]
        bucket.append(signal)
        return signal

    def _live_weight(self, behaviour: str, now: float) -> float:
        live = [s for s in self._signals.get(behaviour, []) if s.alive(now)]
        self._signals[behaviour] = live  # opportunistic decay sweep
        return sum(s.weight for s in live)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, behaviour: str, now: Optional[float] = None) -> BehaviourGate:
        now = time.time() if now is None else now
        gate = self._gates.get(behaviour)
        if gate is None:
            raise QuorumError("unknown behaviour", context={"behaviour": behaviour})

        population = max(self._population_probe(), gate.absolute_floor)
        support = self._live_weight(behaviour, now)
        fraction = support / population

        if gate.state is CollectiveState.DORMANT and fraction >= gate.engage_fraction:
            gate.state = CollectiveState.ENGAGED
            gate.engaged_at = now
            gate.transitions += 1
        elif gate.state is CollectiveState.ENGAGED and fraction < gate.release_fraction:
            gate.state = CollectiveState.DORMANT
            gate.engaged_at = None
            gate.transitions += 1
        return gate

    def evaluate_all(self, now: Optional[float] = None) -> Dict[str, BehaviourGate]:
        now = time.time() if now is None else now
        return {name: self.evaluate(name, now) for name in self._gates}

    def engaged(self, now: Optional[float] = None) -> Tuple[str, ...]:
        now = time.time() if now is None else now
        return tuple(sorted(
            name for name, gate in self.evaluate_all(now).items()
            if gate.state is CollectiveState.ENGAGED
        ))

    def report(self, now: Optional[float] = None) -> Dict[str, Dict[str, object]]:
        now = time.time() if now is None else now
        population = self._population_probe()
        out: Dict[str, Dict[str, object]] = {}
        for name, gate in self._gates.items():
            support = self._live_weight(name, now)
            out[name] = {
                "state": gate.state.value,
                "support": round(support, 3),
                "population": population,
                "fraction": round(support / max(population, 1), 4),
                "transitions": gate.transitions,
            }
        return out
