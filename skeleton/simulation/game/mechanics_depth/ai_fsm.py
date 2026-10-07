"""Deterministic AI behavior FSM."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from skeleton.simulation.game.mechanics_depth.tick_clock import SeededEntropy, TickClock


@dataclass(frozen=True)
class BehaviorState:
    name: str
    aggression: float
    caution: float


@dataclass(frozen=True)
class Transition:
    tick: int
    frm: str
    to: str
    reason: str

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()


class BehaviorFSM:
    def __init__(self, seed: int, *, clock: Optional[TickClock] = None) -> None:
        self.clock = clock or TickClock()
        self.entropy = SeededEntropy(seed)
        self._states: Dict[str, BehaviorState] = {}
        self._edges: Dict[str, Set[str]] = {}
        self._current: Optional[str] = None
        self._log: List[Transition] = []

    def add_state(self, name: str, aggression: float = 0.5, caution: float = 0.5) -> None:
        if not 0 <= aggression <= 1 or not 0 <= caution <= 1:
            raise ValueError("bounds")
        self._states[name] = BehaviorState(name, aggression, caution)
        self._edges.setdefault(name, set())
        if self._current is None:
            self._current = name

    def link(self, frm: str, to: str) -> None:
        if frm not in self._states or to not in self._states:
            raise KeyError("state")
        self._edges[frm].add(to)

    def step(self, stimulus: float) -> Transition:
        if self._current is None:
            raise RuntimeError("empty fsm")
        if not 0 <= stimulus <= 1:
            raise ValueError("stimulus")
        cur = self._states[self._current]
        outs = sorted(self._edges.get(self._current, set()))
        tick = self.clock.advance()
        if not outs:
            tr = Transition(tick, self._current, self._current, "hold")
            self._log.append(tr)
            return tr
        # weighted by aggression vs caution vs stimulus
        scores = []
        for name in outs:
            st = self._states[name]
            score = st.aggression * stimulus + st.caution * (1 - stimulus) + self.entropy.unit() * 0.01
            scores.append((score, name))
        scores.sort(reverse=True)
        nxt = scores[0][1]
        reason = "pursue" if stimulus > 0.6 else ("flee" if stimulus < 0.3 else "patrol")
        tr = Transition(tick, self._current, nxt, reason)
        self._current = nxt
        self._log.append(tr)
        return tr

    def digest(self) -> str:
        body = json.dumps({"current": self._current, "log": [t.digest() for t in self._log]}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()
