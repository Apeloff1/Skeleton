"""B027 combat/abilities as economy flows.

* :class:`AbilityBook` — abilities cost money (a declared sink) and/or
  reagents (an item sink). Using an ability checks *every* cost first and
  then pays them under the economy lock, so a failed cast costs nothing.
* :class:`LootTable` — kills are item and money *faucets*. Drops are chosen
  by a hash of ``(seed, table, kill_id)``, so the same kill always drops the
  same loot on replay and a client cannot reroll by retrying. A per-owner
  rolling window applies diminishing returns to farming: after
  ``full_kills`` kills in ``window_ticks`` each further kill yields half as
  many rolls, down to zero.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import EconomySimError, _req_id, _req_int


@dataclass(frozen=True)
class AbilitySpec:
    ability_id: str
    sink_id: str | None = None
    base: int = 0
    reagent: str | None = None
    reagent_qty: int = 0

    def __post_init__(self) -> None:
        _req_id(self.ability_id, "ability_id")
        if self.sink_id is not None:
            _req_id(self.sink_id, "sink_id")
        _req_int(self.base, "base")
        if (self.reagent is None) != (self.reagent_qty == 0):
            raise EconomySimError("reagent and reagent_qty go together")
        if self.reagent is not None:
            _req_id(self.reagent, "reagent")
            _req_int(self.reagent_qty, "reagent_qty", minimum=1)
        if self.sink_id is None and self.reagent is None:
            raise EconomySimError("ability must cost something")


class AbilityBook:
    def __init__(self, econ: GameplayEconomy, abilities: list[AbilitySpec]) -> None:
        self.econ = econ
        self.abilities: dict[str, AbilitySpec] = {}
        for spec in abilities:
            if spec.ability_id in self.abilities:
                raise EconomySimError("duplicate ability")
            if spec.sink_id is not None and spec.sink_id not in econ.sinks:
                raise EconomySimError(f"unknown sink {spec.sink_id!r}")
            if spec.reagent is not None and spec.reagent not in econ.items:
                raise EconomySimError(f"unknown reagent {spec.reagent!r}")
            self.abilities[spec.ability_id] = spec

    def cost(self, ability_id: str) -> dict[str, Any]:
        spec = self._spec(ability_id)
        money = self.econ.sinks[spec.sink_id].amount_for(spec.base) if spec.sink_id else 0
        return {"money": money, "reagent": spec.reagent, "reagent_qty": spec.reagent_qty}

    def _spec(self, ability_id: str) -> AbilitySpec:
        spec = self.abilities.get(ability_id)
        if spec is None:
            raise EconomySimError("no such ability")
        return spec

    def use(self, owner: str, ability_id: str) -> dict[str, Any]:
        spec = self._spec(ability_id)
        econ = self.econ
        with econ._lock:
            cost = self.cost(ability_id)
            if spec.sink_id is not None:
                currency = econ.sinks[spec.sink_id].currency
                if econ.balance(owner, currency) < cost["money"]:
                    raise EconomySimError("insufficient funds")
            if spec.reagent is not None and econ.inventory(owner).count(spec.reagent) < spec.reagent_qty:
                raise EconomySimError("missing reagents")
            if spec.sink_id is not None:
                econ.charge(spec.sink_id, owner, spec.base)
            if spec.reagent is not None:
                econ.consume_items(f"ability:{ability_id}", owner, spec.reagent, spec.reagent_qty)
            return cost


@dataclass(frozen=True)
class LootEntry:
    item_id: str
    weight: int
    min_qty: int = 1
    max_qty: int = 1

    def __post_init__(self) -> None:
        _req_id(self.item_id, "item_id")
        _req_int(self.weight, "weight", minimum=1)
        _req_int(self.min_qty, "min_qty", minimum=1)
        _req_int(self.max_qty, "max_qty", minimum=self.min_qty)


@dataclass
class LootTable:
    table_id: str
    entries: tuple[LootEntry, ...]
    rolls: int = 1
    bounty_faucet: str | None = None
    full_kills: int = 10
    window_ticks: int = 600
    _kills: dict[str, list[int]] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        _req_id(self.table_id, "table_id")
        if not self.entries:
            raise EconomySimError("loot table is empty")
        _req_int(self.rolls, "rolls", minimum=1)
        _req_int(self.full_kills, "full_kills", minimum=1)
        _req_int(self.window_ticks, "window_ticks", minimum=1)
        self.entries = tuple(self.entries)

    def _rng(self, seed: str, kill_id: str, n: int) -> int:
        h = hashlib.sha256(f"{seed}|{self.table_id}|{kill_id}|{n}".encode()).digest()
        return int.from_bytes(h[:8], "big")

    def roll(self, seed: str, kill_id: str, rolls: int) -> dict[str, int]:
        """Pure, deterministic drop calculation."""
        total = sum(e.weight for e in self.entries)
        drops: dict[str, int] = {}
        for r in range(rolls):
            pick = self._rng(seed, kill_id, 2 * r) % total
            for entry in self.entries:
                if pick < entry.weight:
                    span = entry.max_qty - entry.min_qty + 1
                    qty = entry.min_qty + self._rng(seed, kill_id, 2 * r + 1) % span
                    drops[entry.item_id] = drops.get(entry.item_id, 0) + qty
                    break
                pick -= entry.weight
        return drops

    def effective_rolls(self, owner: str, tick: int) -> int:
        recent = [t for t in self._kills.get(owner, []) if tick - t < self.window_ticks]
        over = len(recent) - self.full_kills + 1
        return self.rolls if over <= 0 else self.rolls >> over

    def award(self, econ: GameplayEconomy, owner: str, kill_id: str, tick: int, *, seed: str) -> dict[str, Any]:
        """Pay out one kill. Each ``kill_id`` pays at most once."""
        _req_int(tick, "tick")
        if not isinstance(kill_id, str) or not kill_id:
            raise EconomySimError("invalid kill_id")
        with econ._lock:
            if kill_id in self._seen:
                raise EconomySimError("kill already looted")
            econ.inventory(owner)
            rolls = self.effective_rolls(owner, tick)
            drops = self.roll(seed, kill_id, rolls) if rolls else {}
            if drops and not econ.fits_many(owner, drops):
                raise EconomySimError("inventory full")
            bounty = 0
            if self.bounty_faucet is not None and rolls:
                try:
                    bounty = econ.grant(self.bounty_faucet, owner, tick)
                except EconomySimError:
                    bounty = 0  # faucet caps/cooldowns throttle bounty, not loot
            for item_id, qty in sorted(drops.items()):
                econ.grant_items(f"loot:{self.table_id}", owner, item_id, qty)
            self._seen.add(kill_id)
            kills = self._kills.setdefault(owner, [])
            kills[:] = [t for t in kills if tick - t < self.window_ticks] + [tick]
            return {"rolls": rolls, "drops": drops, "bounty": bounty}


__all__ = ["AbilityBook", "AbilitySpec", "LootEntry", "LootTable"]
