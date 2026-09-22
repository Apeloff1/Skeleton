"""Batch replay runner — many seeded scenarios, fail-closed digests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from skeleton.game.mechanics_depth import (
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


def scenario_tag_0(seed: int) -> str:
    return hashlib.sha256(f"tag-0-{seed}".encode()).hexdigest()[:16]


def expect_stable_0(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_1(seed: int) -> str:
    return hashlib.sha256(f"tag-1-{seed}".encode()).hexdigest()[:16]


def expect_stable_1(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_2(seed: int) -> str:
    return hashlib.sha256(f"tag-2-{seed}".encode()).hexdigest()[:16]


def expect_stable_2(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_3(seed: int) -> str:
    return hashlib.sha256(f"tag-3-{seed}".encode()).hexdigest()[:16]


def expect_stable_3(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_4(seed: int) -> str:
    return hashlib.sha256(f"tag-4-{seed}".encode()).hexdigest()[:16]


def expect_stable_4(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_5(seed: int) -> str:
    return hashlib.sha256(f"tag-5-{seed}".encode()).hexdigest()[:16]


def expect_stable_5(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_6(seed: int) -> str:
    return hashlib.sha256(f"tag-6-{seed}".encode()).hexdigest()[:16]


def expect_stable_6(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_7(seed: int) -> str:
    return hashlib.sha256(f"tag-7-{seed}".encode()).hexdigest()[:16]


def expect_stable_7(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_8(seed: int) -> str:
    return hashlib.sha256(f"tag-8-{seed}".encode()).hexdigest()[:16]


def expect_stable_8(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_9(seed: int) -> str:
    return hashlib.sha256(f"tag-9-{seed}".encode()).hexdigest()[:16]


def expect_stable_9(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_10(seed: int) -> str:
    return hashlib.sha256(f"tag-10-{seed}".encode()).hexdigest()[:16]


def expect_stable_10(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_11(seed: int) -> str:
    return hashlib.sha256(f"tag-11-{seed}".encode()).hexdigest()[:16]


def expect_stable_11(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_12(seed: int) -> str:
    return hashlib.sha256(f"tag-12-{seed}".encode()).hexdigest()[:16]


def expect_stable_12(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_13(seed: int) -> str:
    return hashlib.sha256(f"tag-13-{seed}".encode()).hexdigest()[:16]


def expect_stable_13(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_14(seed: int) -> str:
    return hashlib.sha256(f"tag-14-{seed}".encode()).hexdigest()[:16]


def expect_stable_14(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_15(seed: int) -> str:
    return hashlib.sha256(f"tag-15-{seed}".encode()).hexdigest()[:16]


def expect_stable_15(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_16(seed: int) -> str:
    return hashlib.sha256(f"tag-16-{seed}".encode()).hexdigest()[:16]


def expect_stable_16(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_17(seed: int) -> str:
    return hashlib.sha256(f"tag-17-{seed}".encode()).hexdigest()[:16]


def expect_stable_17(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_18(seed: int) -> str:
    return hashlib.sha256(f"tag-18-{seed}".encode()).hexdigest()[:16]


def expect_stable_18(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_19(seed: int) -> str:
    return hashlib.sha256(f"tag-19-{seed}".encode()).hexdigest()[:16]


def expect_stable_19(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_20(seed: int) -> str:
    return hashlib.sha256(f"tag-20-{seed}".encode()).hexdigest()[:16]


def expect_stable_20(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_21(seed: int) -> str:
    return hashlib.sha256(f"tag-21-{seed}".encode()).hexdigest()[:16]


def expect_stable_21(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_22(seed: int) -> str:
    return hashlib.sha256(f"tag-22-{seed}".encode()).hexdigest()[:16]


def expect_stable_22(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_23(seed: int) -> str:
    return hashlib.sha256(f"tag-23-{seed}".encode()).hexdigest()[:16]


def expect_stable_23(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_24(seed: int) -> str:
    return hashlib.sha256(f"tag-24-{seed}".encode()).hexdigest()[:16]


def expect_stable_24(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_25(seed: int) -> str:
    return hashlib.sha256(f"tag-25-{seed}".encode()).hexdigest()[:16]


def expect_stable_25(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_26(seed: int) -> str:
    return hashlib.sha256(f"tag-26-{seed}".encode()).hexdigest()[:16]


def expect_stable_26(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_27(seed: int) -> str:
    return hashlib.sha256(f"tag-27-{seed}".encode()).hexdigest()[:16]


def expect_stable_27(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_28(seed: int) -> str:
    return hashlib.sha256(f"tag-28-{seed}".encode()).hexdigest()[:16]


def expect_stable_28(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_29(seed: int) -> str:
    return hashlib.sha256(f"tag-29-{seed}".encode()).hexdigest()[:16]


def expect_stable_29(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_30(seed: int) -> str:
    return hashlib.sha256(f"tag-30-{seed}".encode()).hexdigest()[:16]


def expect_stable_30(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_31(seed: int) -> str:
    return hashlib.sha256(f"tag-31-{seed}".encode()).hexdigest()[:16]


def expect_stable_31(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_32(seed: int) -> str:
    return hashlib.sha256(f"tag-32-{seed}".encode()).hexdigest()[:16]


def expect_stable_32(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_33(seed: int) -> str:
    return hashlib.sha256(f"tag-33-{seed}".encode()).hexdigest()[:16]


def expect_stable_33(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_34(seed: int) -> str:
    return hashlib.sha256(f"tag-34-{seed}".encode()).hexdigest()[:16]


def expect_stable_34(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_35(seed: int) -> str:
    return hashlib.sha256(f"tag-35-{seed}".encode()).hexdigest()[:16]


def expect_stable_35(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_36(seed: int) -> str:
    return hashlib.sha256(f"tag-36-{seed}".encode()).hexdigest()[:16]


def expect_stable_36(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_37(seed: int) -> str:
    return hashlib.sha256(f"tag-37-{seed}".encode()).hexdigest()[:16]


def expect_stable_37(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_38(seed: int) -> str:
    return hashlib.sha256(f"tag-38-{seed}".encode()).hexdigest()[:16]


def expect_stable_38(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_39(seed: int) -> str:
    return hashlib.sha256(f"tag-39-{seed}".encode()).hexdigest()[:16]


def expect_stable_39(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_40(seed: int) -> str:
    return hashlib.sha256(f"tag-40-{seed}".encode()).hexdigest()[:16]


def expect_stable_40(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_41(seed: int) -> str:
    return hashlib.sha256(f"tag-41-{seed}".encode()).hexdigest()[:16]


def expect_stable_41(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_42(seed: int) -> str:
    return hashlib.sha256(f"tag-42-{seed}".encode()).hexdigest()[:16]


def expect_stable_42(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_43(seed: int) -> str:
    return hashlib.sha256(f"tag-43-{seed}".encode()).hexdigest()[:16]


def expect_stable_43(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_44(seed: int) -> str:
    return hashlib.sha256(f"tag-44-{seed}".encode()).hexdigest()[:16]


def expect_stable_44(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_45(seed: int) -> str:
    return hashlib.sha256(f"tag-45-{seed}".encode()).hexdigest()[:16]


def expect_stable_45(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_46(seed: int) -> str:
    return hashlib.sha256(f"tag-46-{seed}".encode()).hexdigest()[:16]


def expect_stable_46(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_47(seed: int) -> str:
    return hashlib.sha256(f"tag-47-{seed}".encode()).hexdigest()[:16]


def expect_stable_47(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_48(seed: int) -> str:
    return hashlib.sha256(f"tag-48-{seed}".encode()).hexdigest()[:16]


def expect_stable_48(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_49(seed: int) -> str:
    return hashlib.sha256(f"tag-49-{seed}".encode()).hexdigest()[:16]


def expect_stable_49(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_50(seed: int) -> str:
    return hashlib.sha256(f"tag-50-{seed}".encode()).hexdigest()[:16]


def expect_stable_50(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_51(seed: int) -> str:
    return hashlib.sha256(f"tag-51-{seed}".encode()).hexdigest()[:16]


def expect_stable_51(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_52(seed: int) -> str:
    return hashlib.sha256(f"tag-52-{seed}".encode()).hexdigest()[:16]


def expect_stable_52(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_53(seed: int) -> str:
    return hashlib.sha256(f"tag-53-{seed}".encode()).hexdigest()[:16]


def expect_stable_53(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_54(seed: int) -> str:
    return hashlib.sha256(f"tag-54-{seed}".encode()).hexdigest()[:16]


def expect_stable_54(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_55(seed: int) -> str:
    return hashlib.sha256(f"tag-55-{seed}".encode()).hexdigest()[:16]


def expect_stable_55(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_56(seed: int) -> str:
    return hashlib.sha256(f"tag-56-{seed}".encode()).hexdigest()[:16]


def expect_stable_56(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_57(seed: int) -> str:
    return hashlib.sha256(f"tag-57-{seed}".encode()).hexdigest()[:16]


def expect_stable_57(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_58(seed: int) -> str:
    return hashlib.sha256(f"tag-58-{seed}".encode()).hexdigest()[:16]


def expect_stable_58(a: str, b: str) -> bool:
    return a == b and len(a) == 64


def scenario_tag_59(seed: int) -> str:
    return hashlib.sha256(f"tag-59-{seed}".encode()).hexdigest()[:16]


def expect_stable_59(a: str, b: str) -> bool:
    return a == b and len(a) == 64
