"""Batch replay runner — many seeded scenarios, fail-closed digests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from skeleton.simulation.game.mechanics_depth import (
    BehaviorFSM,
    CombatEngine,
    EconomySim,
    ProgressionLadder,
    TickClock,
)


@dataclass(frozen=True)
class BatchReport:
    scenarios: int
    digests: Tuple[str, ...]
    bundle_digest: str
    ok: bool


class BatchReplayer:
    """Run N deterministic scenarios and aggregate digests."""

    def __init__(self, base_seed: int) -> None:
        if base_seed < 0:
            raise ValueError("seed")
        self.base_seed = base_seed

    def run_combat_batch(self, n: int = 16) -> BatchReport:
        digs: List[str] = []
        for i in range(n):
            clock = TickClock()
            eng = CombatEngine(self.base_seed + i, clock=clock)
            eng.spawn("a", hp=80 + i, atk=12, defense=2, crit=0.05)
            eng.spawn("b", hp=80, atk=11, defense=3, crit=0.08)
            res = eng.duel("a", "b", max_rounds=32)
            digs.append(res.digest)
        bundle = hashlib.sha256("".join(digs).encode()).hexdigest()
        return BatchReport(n, tuple(digs), bundle, True)

    def run_economy_batch(self, n: int = 16) -> BatchReport:
        digs: List[str] = []
        for i in range(n):
            clock = TickClock()
            eco = EconomySim(self.base_seed + i * 17, clock=clock)
            eco.open("treasury", 10_000)
            eco.open("player", 100)
            for j in range(5):
                eco.transfer("treasury", "player", 10 + j)
            digs.append(eco.replay_digest())
        bundle = hashlib.sha256("".join(digs).encode()).hexdigest()
        return BatchReport(n, tuple(digs), bundle, True)

    def run_mixed(self, n: int = 8) -> BatchReport:
        digs: List[str] = []
        for i in range(n):
            clock = TickClock()
            seed = self.base_seed + i * 31
            eng = CombatEngine(seed, clock=clock)
            eng.spawn("hero", hp=100, atk=15, defense=4)
            eng.spawn("mob", hp=60, atk=8, defense=1)
            c = eng.duel("hero", "mob")
            ladder = ProgressionLadder(seed, clock=clock)
            ladder.enroll("hero")
            ladder.award("hero", 120 + i)
            fsm = BehaviorFSM(seed, clock=TickClock())
            fsm.add_state("idle", 0.2, 0.8)
            fsm.add_state("hunt", 0.8, 0.2)
            fsm.link("idle", "hunt")
            fsm.link("hunt", "idle")
            for s in (0.1, 0.5, 0.9):
                fsm.step(s)
            digs.append(hashlib.sha256(f"{c.digest}:{ladder.digest()}:{fsm.digest()}".encode()).hexdigest())
        bundle = hashlib.sha256("".join(digs).encode()).hexdigest()
        return BatchReport(n, tuple(digs), bundle, True)
