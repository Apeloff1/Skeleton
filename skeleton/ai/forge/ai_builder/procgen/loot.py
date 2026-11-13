"""Loot tables driven by the economy modules.

No prices or drop weights are invented here. Item values come from
``skeleton.simulation.economy.sim.ItemSpec`` (``vendor_sell_price``, falling
back to ``vendor_buy_price``) on an :class:`EconomySim`; drop weights come
from a balanced ``skeleton.simulation.economy.harbor.Harbor`` when one is
given (keys are item ids), else are derived inversely from value so rare means
valuable. Currency drops reuse the sim's declared faucet amounts. Per-room
budgets are a multiple of the *median* item value, scaled by the room's
encounter risk, so loot follows danger.

Anything that can answer :class:`LootSource` can be injected instead
(tests use a plain fake), so procgen does not depend on a live sim.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence, runtime_checkable

from skeleton.simulation.ecs.rng import DeterministicRng

from .canonical import digest, q
from .errors import ProcgenError


@dataclass(frozen=True)
class LootEntry:
    item_id: str
    currency: str
    value: int
    weight: float
    max_stack: int = 1


@dataclass(frozen=True)
class CurrencyDrop:
    currency: str
    amount: int


@runtime_checkable
class LootSource(Protocol):
    """What procgen needs from an economy: priced items with weights, and currency drop sizes."""

    def entries(self) -> Sequence[LootEntry]: ...

    def currency_drops(self) -> Sequence[CurrencyDrop]: ...

    def describe(self) -> Mapping[str, object]: ...


class EconomyLootSource:
    """Adapter over ``EconomySim`` (+ optional ``Harbor``)."""

    def __init__(self, sim, harbor=None, *, tradeable_only: bool = False) -> None:
        self._sim = sim
        self._harbor = harbor
        self._tradeable_only = tradeable_only
        self._entries = self._build()

    @staticmethod
    def _value(spec) -> int | None:
        return spec.vendor_sell_price if spec.vendor_sell_price is not None else spec.vendor_buy_price

    def _build(self) -> tuple[LootEntry, ...]:
        priced = []
        for iid in sorted(self._sim.items):
            spec = self._sim.items[iid]
            if self._tradeable_only and not spec.tradeable:
                continue
            v = self._value(spec)
            if v is None or v <= 0:
                continue
            priced.append((spec, int(v)))
        if not priced:
            return ()
        weights = self._harbor_weights({s.item_id for s, _ in priced})
        out = []
        for spec, v in priced:
            w = weights[spec.item_id] if weights is not None else 1.0 / v
            out.append(LootEntry(spec.item_id, spec.currency, v, float(w), int(spec.max_stack)))
        return tuple(out)

    def _harbor_weights(self, ids: set[str]) -> dict[str, float] | None:
        h = self._harbor
        if h is None or not h.balanced():
            return None
        w = {k: float(v) for k, v in h.weights.items() if k in ids and v > 0}
        if set(w) != ids:
            return None  # harbor does not cover the priced items; fall back to value-derived weights
        return w

    def entries(self) -> Sequence[LootEntry]:
        return self._entries

    def currency_drops(self) -> Sequence[CurrencyDrop]:
        return tuple(CurrencyDrop(f.currency, int(f.amount))
                     for _, f in sorted(self._sim.faucets.items()))

    def describe(self) -> Mapping[str, object]:
        return {"source": "skeleton.simulation.economy.sim.EconomySim",
                "weights": "harbor" if self._harbor_weights({e.item_id for e in self._entries}) else "inverse_value",
                "items": len(self._entries), "currencies": sorted(self._sim.currencies)}


@dataclass(frozen=True)
class LootConfig:
    budget_medians: float = 1.5      # room budget at risk 1.0, in median item values
    min_risk: float = 0.15           # rooms with no fights still roll a little
    max_items: int = 4
    currency_share: float = 0.5      # chance a room also drops a currency faucet's amount
    goal_bonus: float = 2.0

    def __post_init__(self) -> None:
        if self.budget_medians <= 0 or not 0 <= self.min_risk <= 1 or not 1 <= self.max_items <= 16:
            raise ProcgenError("invalid loot config")
        if not 0 <= self.currency_share <= 1 or self.goal_bonus < 1:
            raise ProcgenError("invalid loot config")


@dataclass(frozen=True)
class Drop:
    item_id: str
    qty: int
    value: int        # total value of the stack

    def as_dict(self) -> dict:
        return {"item": self.item_id, "qty": self.qty, "value": self.value}


@dataclass(frozen=True)
class RoomLoot:
    room: str
    risk: float
    budget: float
    drops: tuple[Drop, ...]
    currency: tuple[CurrencyDrop, ...]

    @property
    def value(self) -> int:
        return sum(d.value for d in self.drops)

    def as_dict(self) -> dict:
        return {"room": self.room, "risk": self.risk, "budget": self.budget, "value": self.value,
                "drops": [d.as_dict() for d in self.drops],
                "currency": [{"currency": c.currency, "amount": c.amount} for c in self.currency]}


@dataclass(frozen=True)
class LootPlan:
    rooms: Mapping[str, RoomLoot]
    median_value: float
    source: Mapping[str, object]

    def total(self) -> int:
        return sum(r.value for r in self.rooms.values())

    def as_dict(self) -> dict:
        return {"median_value": self.median_value, "source": dict(self.source), "total": self.total(),
                "rooms": {k: v.as_dict() for k, v in sorted(self.rooms.items())}}

    def digest(self) -> str:
        return digest(self.as_dict())


def median_value(source: LootSource) -> float:
    vals = [e.value for e in source.entries()]
    if not vals:
        raise ProcgenError("loot source has no priced items")
    return float(statistics.median(vals))


def roll_room(room: str, risk: float, source: LootSource, rng: DeterministicRng, cfg: LootConfig,
              med: float, *, goal: bool = False) -> RoomLoot:
    risk = min(max(risk, cfg.min_risk), 1.0)
    budget = q(cfg.budget_medians * med * risk * (cfg.goal_bonus if goal else 1.0))
    remaining = budget
    drops: dict[str, list[int]] = {}
    entries = sorted(source.entries(), key=lambda e: e.item_id)
    for _ in range(cfg.max_items):
        fit = [e for e in entries if e.value <= remaining]
        if not fit:
            break
        e = fit[rng.weighted_index([x.weight for x in fit])]
        cur = drops.setdefault(e.item_id, [0, e.value, e.max_stack])
        if cur[0] >= e.max_stack:
            entries = [x for x in entries if x.item_id != e.item_id]
            continue
        cur[0] += 1
        remaining -= e.value
    out = tuple(Drop(k, v[0], v[0] * v[1]) for k, v in sorted(drops.items()) if v[0] > 0)
    cur_drops: tuple[CurrencyDrop, ...] = ()
    faucets = list(source.currency_drops())
    if faucets and rng.chance(cfg.currency_share * risk):
        cur_drops = (faucets[rng.randint(0, len(faucets) - 1)],)
    return RoomLoot(room, q(risk), budget, out, cur_drops)


def place_loot(risk_by_room: Mapping[str, float], source: LootSource, rng: DeterministicRng,
               cfg: LootConfig = LootConfig(), *, goal: str | None = None) -> LootPlan:
    if not isinstance(source, LootSource):
        raise ProcgenError("source must implement LootSource")
    med = median_value(source)
    rooms = {rid: roll_room(rid, risk_by_room[rid], source, rng.fork(f"room/{rid}"), cfg, med, goal=(rid == goal))
             for rid in sorted(risk_by_room)}
    return LootPlan(rooms, med, source.describe())


def risk_value_correlation(plan: LootPlan) -> float:
    """Spearman-ish rank correlation between room risk and loot value (1 = loot follows risk)."""
    rows = sorted(plan.rooms.values(), key=lambda r: r.room)
    if len(rows) < 3:
        return 1.0

    def ranks(xs: list[float]) -> list[float]:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    a = ranks([r.risk for r in rows])
    b = ranks([float(r.value) for r in rows])
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return q(num / den) if den else 0.0
