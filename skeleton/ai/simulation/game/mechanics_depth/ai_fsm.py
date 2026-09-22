"""Deterministic AI behavior FSM."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from skeleton.game.mechanics_depth.tick_clock import SeededEntropy, TickClock


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


def stimulus_curve_0(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 0 * 0.001))


def aggression_bias_0(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 0 * 0.002))


def stimulus_curve_1(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 1 * 0.001))


def aggression_bias_1(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 1 * 0.002))


def stimulus_curve_2(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 2 * 0.001))


def aggression_bias_2(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 2 * 0.002))


def stimulus_curve_3(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 3 * 0.001))


def aggression_bias_3(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 3 * 0.002))


def stimulus_curve_4(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 4 * 0.001))


def aggression_bias_4(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 4 * 0.002))


def stimulus_curve_5(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 5 * 0.001))


def aggression_bias_5(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 5 * 0.002))


def stimulus_curve_6(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 6 * 0.001))


def aggression_bias_6(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 6 * 0.002))


def stimulus_curve_7(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 7 * 0.001))


def aggression_bias_7(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 7 * 0.002))


def stimulus_curve_8(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 8 * 0.001))


def aggression_bias_8(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 8 * 0.002))


def stimulus_curve_9(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 9 * 0.001))


def aggression_bias_9(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 9 * 0.002))


def stimulus_curve_10(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 10 * 0.001))


def aggression_bias_10(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 10 * 0.002))


def stimulus_curve_11(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 11 * 0.001))


def aggression_bias_11(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 11 * 0.002))


def stimulus_curve_12(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 12 * 0.001))


def aggression_bias_12(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 12 * 0.002))


def stimulus_curve_13(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 13 * 0.001))


def aggression_bias_13(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 13 * 0.002))


def stimulus_curve_14(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 14 * 0.001))


def aggression_bias_14(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 14 * 0.002))


def stimulus_curve_15(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 15 * 0.001))


def aggression_bias_15(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 15 * 0.002))


def stimulus_curve_16(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 16 * 0.001))


def aggression_bias_16(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 16 * 0.002))


def stimulus_curve_17(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 17 * 0.001))


def aggression_bias_17(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 17 * 0.002))


def stimulus_curve_18(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 18 * 0.001))


def aggression_bias_18(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 18 * 0.002))


def stimulus_curve_19(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 19 * 0.001))


def aggression_bias_19(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 19 * 0.002))


def stimulus_curve_20(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 20 * 0.001))


def aggression_bias_20(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 20 * 0.002))


def stimulus_curve_21(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 21 * 0.001))


def aggression_bias_21(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 21 * 0.002))


def stimulus_curve_22(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 22 * 0.001))


def aggression_bias_22(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 22 * 0.002))


def stimulus_curve_23(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 23 * 0.001))


def aggression_bias_23(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 23 * 0.002))


def stimulus_curve_24(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 24 * 0.001))


def aggression_bias_24(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 24 * 0.002))


def stimulus_curve_25(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 25 * 0.001))


def aggression_bias_25(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 25 * 0.002))


def stimulus_curve_26(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 26 * 0.001))


def aggression_bias_26(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 26 * 0.002))


def stimulus_curve_27(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 27 * 0.001))


def aggression_bias_27(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 27 * 0.002))


def stimulus_curve_28(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 28 * 0.001))


def aggression_bias_28(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 28 * 0.002))


def stimulus_curve_29(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 29 * 0.001))


def aggression_bias_29(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 29 * 0.002))


def stimulus_curve_30(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 30 * 0.001))


def aggression_bias_30(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 30 * 0.002))


def stimulus_curve_31(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 31 * 0.001))


def aggression_bias_31(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 31 * 0.002))


def stimulus_curve_32(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 32 * 0.001))


def aggression_bias_32(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 32 * 0.002))


def stimulus_curve_33(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 33 * 0.001))


def aggression_bias_33(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 33 * 0.002))


def stimulus_curve_34(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 34 * 0.001))


def aggression_bias_34(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 34 * 0.002))


def stimulus_curve_35(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 35 * 0.001))


def aggression_bias_35(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 35 * 0.002))


def stimulus_curve_36(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 36 * 0.001))


def aggression_bias_36(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 36 * 0.002))


def stimulus_curve_37(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 37 * 0.001))


def aggression_bias_37(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 37 * 0.002))


def stimulus_curve_38(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 38 * 0.001))


def aggression_bias_38(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 38 * 0.002))


def stimulus_curve_39(t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("t")
    return min(1.0, max(0.0, t * t * (3 - 2 * t) + 39 * 0.001))


def aggression_bias_39(base: float, threat: float) -> float:
    if not 0 <= base <= 1 or not 0 <= threat <= 1:
        raise ValueError("bounds")
    return min(1.0, base + threat * (0.2 + 39 * 0.002))
