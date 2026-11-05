"""B028 quest rewards as a governed faucet.

Quest rewards are the largest designer-controlled faucet in most games, so
:class:`QuestBoard` makes them auditable and non-farmable:

* a quest pays once per owner, unless ``repeat_ticks`` is set, in which case
  it pays at most once per ``repeat_ticks``;
* prerequisites must be completed first;
* item reward capacity is checked *before* any money is minted, and the
  money reward goes through the economy's declared faucet (with its own
  cooldown/window/supply caps), so a refused claim pays nothing;
* item rewards are minted under ``quest:<quest_id>`` and appear in item
  flow reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import EconomySimError, _req_id, _req_int


@dataclass(frozen=True)
class QuestSpec:
    quest_id: str
    reward_faucet: str | None = None
    reward_items: Mapping[str, int] = field(default_factory=dict)
    prerequisites: tuple[str, ...] = ()
    repeat_ticks: int | None = None

    def __post_init__(self) -> None:
        _req_id(self.quest_id, "quest_id")
        if self.reward_faucet is not None:
            _req_id(self.reward_faucet, "reward_faucet")
        for item_id, qty in self.reward_items.items():
            _req_id(item_id, "reward item")
            _req_int(qty, "reward qty", minimum=1)
        if self.repeat_ticks is not None:
            _req_int(self.repeat_ticks, "repeat_ticks", minimum=1)
        if self.quest_id in self.prerequisites:
            raise EconomySimError("quest cannot require itself")
        object.__setattr__(self, "reward_items", dict(sorted(self.reward_items.items())))
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))


class QuestBoard:
    def __init__(self, econ: GameplayEconomy, quests: list[QuestSpec]) -> None:
        self.econ = econ
        self.quests: dict[str, QuestSpec] = {}
        for q in quests:
            if q.quest_id in self.quests:
                raise EconomySimError("duplicate quest")
            if q.reward_faucet is not None and q.reward_faucet not in econ.faucets:
                raise EconomySimError(f"unknown faucet {q.reward_faucet!r}")
            for item_id in q.reward_items:
                if item_id not in econ.items:
                    raise EconomySimError(f"unknown item {item_id!r}")
            self.quests[q.quest_id] = q
        for q in self.quests.values():
            for pre in q.prerequisites:
                if pre not in self.quests:
                    raise EconomySimError(f"unknown prerequisite {pre!r}")
        self._check_acyclic()
        self._completed: dict[tuple[str, str], int] = {}

    def _check_acyclic(self) -> None:
        state: dict[str, int] = {}

        def visit(qid: str) -> None:
            if state.get(qid) == 1:
                raise EconomySimError("quest prerequisites form a cycle")
            if state.get(qid) == 2:
                return
            state[qid] = 1
            for pre in self.quests[qid].prerequisites:
                visit(pre)
            state[qid] = 2

        for qid in sorted(self.quests):
            visit(qid)

    def completed(self, owner: str, quest_id: str) -> bool:
        return (owner, quest_id) in self._completed

    def complete(self, owner: str, quest_id: str, tick: int) -> dict[str, Any]:
        _req_int(tick, "tick")
        spec = self.quests.get(quest_id)
        if spec is None:
            raise EconomySimError("no such quest")
        econ = self.econ
        with econ._lock:
            econ.inventory(owner)
            last = self._completed.get((owner, quest_id))
            if last is not None:
                if spec.repeat_ticks is None:
                    raise EconomySimError("quest already completed")
                if tick < last:
                    raise EconomySimError("tick went backwards")
                if tick - last < spec.repeat_ticks:
                    raise EconomySimError("quest not yet repeatable")
            missing = [p for p in spec.prerequisites if not self.completed(owner, p)]
            if missing:
                raise EconomySimError(f"prerequisites missing: {missing}")
            if spec.reward_items and not econ.fits_many(owner, spec.reward_items):
                raise EconomySimError("inventory full")
            money = econ.grant(spec.reward_faucet, owner, tick) if spec.reward_faucet else 0
            for item_id, qty in spec.reward_items.items():
                econ.grant_items(f"quest:{quest_id}", owner, item_id, qty)
            self._completed[(owner, quest_id)] = tick
            return {"money": money, "items": dict(spec.reward_items)}


__all__ = ["QuestBoard", "QuestSpec"]
