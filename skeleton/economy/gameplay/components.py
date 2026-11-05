"""B022 economy components and systems in ECS style.

Entities (structures, mounts, hirelings, plots) carry plain-data components;
systems iterate them in sorted entity order every tick so a run is
deterministic. Two systems ship here:

* :class:`UpkeepSystem` — a recurring *sink*: each entity with an
  :class:`Upkeep` charges its owner a declared sink every ``every_ticks``.
  A missed payment adds a :class:`Delinquent` component instead of raising;
  after ``grace`` consecutive misses the entity is marked ``repossessed`` and
  stops charging (and stops earning).
* :class:`IncomeSystem` — a recurring *faucet*: entities with :class:`Income`
  claim a declared faucet when due. Faucet cooldowns/caps still apply; a
  refused grant is reported, not raised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import EconomySimError, _req_id, _req_int


@dataclass(frozen=True)
class Owned:
    owner: str


@dataclass(frozen=True)
class Upkeep:
    sink_id: str
    every_ticks: int
    base: int = 0
    grace: int = 3

    def __post_init__(self) -> None:
        _req_id(self.sink_id, "sink_id")
        _req_int(self.every_ticks, "every_ticks", minimum=1)
        _req_int(self.base, "base")
        _req_int(self.grace, "grace", minimum=1)


@dataclass(frozen=True)
class Income:
    faucet_id: str
    every_ticks: int

    def __post_init__(self) -> None:
        _req_id(self.faucet_id, "faucet_id")
        _req_int(self.every_ticks, "every_ticks", minimum=1)


@dataclass
class Delinquent:
    misses: int = 0
    repossessed: bool = False


COMPONENT_TYPES = (Owned, Upkeep, Income, Delinquent)


class EconomyWorld:
    """Minimal component store: entity id -> {component type -> instance}."""

    def __init__(self) -> None:
        self._entities: dict[str, dict[type, Any]] = {}
        self._due: dict[tuple[str, type], int] = {}

    def spawn(self, entity: str, *components: Any, tick: int = 0) -> None:
        _req_id(entity, "entity")
        _req_int(tick, "tick")
        if entity in self._entities:
            raise EconomySimError("entity exists")
        self._entities[entity] = {}
        for component in components:
            self.add(entity, component, tick=tick)

    def add(self, entity: str, component: Any, *, tick: int = 0) -> None:
        if type(component) not in COMPONENT_TYPES:
            raise EconomySimError(f"unknown component {type(component).__name__}")
        comps = self._get(entity)
        comps[type(component)] = component
        if isinstance(component, (Upkeep, Income)):
            self._due[(entity, type(component))] = tick + component.every_ticks

    def despawn(self, entity: str) -> None:
        self._get(entity)
        del self._entities[entity]
        for key in [k for k in self._due if k[0] == entity]:
            del self._due[key]

    def _get(self, entity: str) -> dict[type, Any]:
        comps = self._entities.get(entity)
        if comps is None:
            raise EconomySimError("no such entity")
        return comps

    def get(self, entity: str, ctype: type) -> Any | None:
        return self._get(entity).get(ctype)

    def query(self, *ctypes: type) -> list[tuple[str, tuple[Any, ...]]]:
        out = []
        for entity in sorted(self._entities):
            comps = self._entities[entity]
            if all(c in comps for c in ctypes):
                out.append((entity, tuple(comps[c] for c in ctypes)))
        return out

    def due(self, entity: str, ctype: type, tick: int) -> bool:
        return self._due.get((entity, ctype), tick + 1) <= tick

    def advance(self, entity: str, ctype: type, every: int) -> None:
        self._due[(entity, ctype)] += every

    def is_active(self, entity: str) -> bool:
        delinquent = self.get(entity, Delinquent)
        return delinquent is None or not delinquent.repossessed


class UpkeepSystem:
    def run(self, world: EconomyWorld, econ: GameplayEconomy, tick: int) -> dict[str, list[str]]:
        _req_int(tick, "tick")
        report: dict[str, list[str]] = {"paid": [], "missed": [], "repossessed": []}
        for entity, (owned, upkeep) in world.query(Owned, Upkeep):
            if not world.is_active(entity):
                continue
            while world.due(entity, Upkeep, tick):
                world.advance(entity, Upkeep, upkeep.every_ticks)
                try:
                    econ.charge(upkeep.sink_id, owned.owner, upkeep.base)
                except EconomySimError:
                    delinquent = world.get(entity, Delinquent) or Delinquent()
                    delinquent.misses += 1
                    world.add(entity, delinquent)
                    if delinquent.misses >= upkeep.grace:
                        delinquent.repossessed = True
                        report["repossessed"].append(entity)
                        break
                    report["missed"].append(entity)
                else:
                    delinquent = world.get(entity, Delinquent)
                    if delinquent is not None:
                        delinquent.misses = 0
                    report["paid"].append(entity)
        return report


class IncomeSystem:
    def run(self, world: EconomyWorld, econ: GameplayEconomy, tick: int) -> dict[str, list[str]]:
        _req_int(tick, "tick")
        report: dict[str, list[str]] = {"paid": [], "refused": []}
        for entity, (owned, income) in world.query(Owned, Income):
            if not world.is_active(entity) or not world.due(entity, Income, tick):
                continue
            # Income never back-pays missed periods: one claim, then reschedule.
            while world.due(entity, Income, tick):
                world.advance(entity, Income, income.every_ticks)
            try:
                econ.grant(income.faucet_id, owned.owner, tick)
            except EconomySimError:
                report["refused"].append(entity)
            else:
                report["paid"].append(entity)
        return report


__all__ = [
    "Delinquent",
    "EconomyWorld",
    "Income",
    "IncomeSystem",
    "Owned",
    "Upkeep",
    "UpkeepSystem",
]
