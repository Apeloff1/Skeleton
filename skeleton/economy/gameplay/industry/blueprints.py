"""Blueprints (recipes) and multi-step production-chain planning.

A :class:`Blueprint` turns integer quantities of input items into a fixed
output quantity of one item in ``base_ticks`` ticks. Every blueprint carries
a base ``waste_bps``: extra material destroyed on top of the inputs (the
crafting-loss sink). Research (:mod:`.research`) lowers both waste and time.

:class:`BlueprintBook` validates blueprints against an economy's item specs,
refuses cycles, and :meth:`BlueprintBook.plan` expands a target into an
ordered list of production steps (deepest intermediates first) plus the raw
materials the whole chain needs. Planning is pure and deterministic: inputs
are walked in sorted order and integer ceilings are used for runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.economy.gameplay.industry.errors import IndustryError
from skeleton.simulation.economy.sim import BPS, _req_id, _req_int

MAX_WASTE_BPS = 5_000


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


@dataclass(frozen=True)
class Blueprint:
    blueprint_id: str
    output: str
    output_qty: int
    inputs: tuple[tuple[str, int], ...]
    base_ticks: int
    waste_bps: int = 0
    max_research: int = 10
    me_step_bps: int = 1_000
    te_step_bps: int = 400
    min_ticks: int = 1

    def __post_init__(self) -> None:
        _req_id(self.blueprint_id, "blueprint_id")
        _req_id(self.output, "output item")
        _req_int(self.output_qty, "output_qty", minimum=1)
        _req_int(self.base_ticks, "base_ticks", minimum=1)
        _req_int(self.min_ticks, "min_ticks", minimum=1)
        _req_int(self.waste_bps, "waste_bps")
        _req_int(self.max_research, "max_research")
        _req_int(self.me_step_bps, "me_step_bps")
        _req_int(self.te_step_bps, "te_step_bps")
        if self.waste_bps > MAX_WASTE_BPS:
            raise IndustryError("waste_bps above 50%")
        if self.me_step_bps > BPS or self.te_step_bps * self.max_research >= BPS:
            raise IndustryError("research steps would remove all time or waste")
        if not self.inputs:
            raise IndustryError("blueprint needs at least one input")
        seen = set()
        for item_id, qty in self.inputs:
            _req_id(item_id, "input item")
            _req_int(qty, "input qty", minimum=1)
            if item_id in seen:
                raise IndustryError(f"duplicate input {item_id!r}")
            if item_id == self.output:
                raise IndustryError("blueprint consumes its own output")
            seen.add(item_id)
        object.__setattr__(self, "inputs", tuple(sorted(self.inputs)))

    # -- efficiency ---------------------------------------------------------
    def waste_at(self, me_level: int) -> int:
        """Waste in bps after ``me_level`` material-efficiency research."""
        _req_int(me_level, "me_level")
        level = min(me_level, self.max_research)
        return self.waste_bps * max(BPS - self.me_step_bps * level, 0) // BPS

    def ticks_at(self, te_level: int, runs: int = 1) -> int:
        """Ticks for ``runs`` runs after ``te_level`` time-efficiency research."""
        _req_int(te_level, "te_level")
        _req_int(runs, "runs", minimum=1)
        level = min(te_level, self.max_research)
        per = self.base_ticks * (BPS - self.te_step_bps * level)
        return max(self.min_ticks, ceil_div(per * runs, BPS))

    def materials(self, runs: int, me_level: int = 0) -> dict[str, dict[str, int]]:
        """Per input: ``{"used": n, "lost": m}`` for ``runs`` runs.

        ``used`` ends up in the product, ``lost`` is the waste sink, rounded
        up per input so loss is never silently zero when waste is non-zero.
        """
        _req_int(runs, "runs", minimum=1)
        waste = self.waste_at(me_level)
        out: dict[str, dict[str, int]] = {}
        for item_id, qty in self.inputs:
            used = qty * runs
            lost = ceil_div(used * waste, BPS) if waste else 0
            out[item_id] = {"used": used, "lost": lost}
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "output": self.output,
            "output_qty": self.output_qty,
            "inputs": [list(i) for i in self.inputs],
            "base_ticks": self.base_ticks,
            "waste_bps": self.waste_bps,
            "max_research": self.max_research,
            "me_step_bps": self.me_step_bps,
            "te_step_bps": self.te_step_bps,
            "min_ticks": self.min_ticks,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Blueprint":
        kw = dict(data)
        kw["inputs"] = tuple((str(i), int(q)) for i, q in kw["inputs"])
        return cls(**kw)


@dataclass(frozen=True)
class PlanStep:
    blueprint_id: str
    output: str
    runs: int
    depth: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "output": self.output,
            "runs": self.runs,
            "depth": self.depth,
        }


@dataclass
class ChainPlan:
    target: str
    qty: int
    steps: list[PlanStep] = field(default_factory=list)
    raw: dict[str, int] = field(default_factory=dict)
    lost: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "qty": self.qty,
            "steps": [s.to_dict() for s in self.steps],
            "raw": dict(sorted(self.raw.items())),
            "lost": dict(sorted(self.lost.items())),
        }


class BlueprintBook:
    """Registry of blueprints, at most one producer per output item."""

    def __init__(
        self,
        blueprints: Iterable[Blueprint] = (),
        *,
        items: Iterable[str] | None = None,
    ):
        self._known_items = None if items is None else frozenset(items)
        self._by_id: dict[str, Blueprint] = {}
        self._by_output: dict[str, str] = {}
        for bp in blueprints:
            self.add(bp)

    def add(self, bp: Blueprint) -> None:
        if bp.blueprint_id in self._by_id:
            raise IndustryError(f"duplicate blueprint {bp.blueprint_id!r}")
        if bp.output in self._by_output:
            raise IndustryError(f"{bp.output!r} already has a producer")
        if self._known_items is not None:
            for item_id in [bp.output, *(i for i, _ in bp.inputs)]:
                if item_id not in self._known_items:
                    raise IndustryError(f"blueprint uses unknown item {item_id!r}")
        self._by_id[bp.blueprint_id] = bp
        self._by_output[bp.output] = bp.blueprint_id
        try:
            self._check_acyclic(bp.output)
        except IndustryError:
            del self._by_id[bp.blueprint_id]
            del self._by_output[bp.output]
            raise

    def _check_acyclic(self, start: str) -> None:
        stack: list[tuple[str, tuple[str, ...]]] = [(start, (start,))]
        while stack:
            item_id, path = stack.pop()
            bp = self.producer(item_id)
            if bp is None:
                continue
            for child, _ in bp.inputs:
                if child in path:
                    raise IndustryError("production chain has a cycle")
                stack.append((child, path + (child,)))

    def __contains__(self, blueprint_id: object) -> bool:
        return blueprint_id in self._by_id

    def get(self, blueprint_id: str) -> Blueprint:
        bp = self._by_id.get(blueprint_id)
        if bp is None:
            raise IndustryError("no such blueprint")
        return bp

    def producer(self, item_id: str) -> Blueprint | None:
        bid = self._by_output.get(item_id)
        return None if bid is None else self._by_id[bid]

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def depth(self, item_id: str) -> int:
        """0 for raw materials, else 1 + deepest input."""
        bp = self.producer(item_id)
        if bp is None:
            return 0
        return 1 + max(self.depth(i) for i, _ in bp.inputs)

    def plan(
        self, target: str, qty: int, levels: Mapping[str, tuple[int, int]] | None = None
    ) -> ChainPlan:
        """Expand ``qty`` of ``target`` into steps and raw needs.

        ``levels`` maps blueprint id to ``(me, te)`` research levels. Every
        intermediate is produced fresh (stock on hand is not netted out) so
        the plan is a pure function of the book and the levels.
        """
        _req_int(qty, "qty", minimum=1)
        if self.producer(target) is None:
            raise IndustryError(f"no blueprint produces {target!r}")
        levels = dict(levels or {})
        need: dict[str, int] = {target: qty}
        plan = ChainPlan(target, qty)
        runs_by_bp: dict[str, int] = {}
        # process items from highest depth down so each item's demand is final
        order = sorted(self._closure(target), key=lambda i: (-self.depth(i), i))
        for item_id in order:
            demand = need.get(item_id, 0)
            bp = self.producer(item_id)
            if bp is None or demand == 0:
                continue
            runs = ceil_div(demand, bp.output_qty)
            runs_by_bp[bp.blueprint_id] = runs
            me = levels.get(bp.blueprint_id, (0, 0))[0]
            for child, row in bp.materials(runs, me).items():
                need[child] = need.get(child, 0) + row["used"] + row["lost"]
                if row["lost"]:
                    plan.lost[child] = plan.lost.get(child, 0) + row["lost"]
        for item_id in sorted(self._closure(target), key=lambda i: (self.depth(i), i)):
            bp = self.producer(item_id)
            if bp is None:
                plan.raw[item_id] = need.get(item_id, 0)
            elif bp.blueprint_id in runs_by_bp:
                plan.steps.append(
                    PlanStep(
                        bp.blueprint_id,
                        item_id,
                        runs_by_bp[bp.blueprint_id],
                        self.depth(item_id),
                    )
                )
        return plan

    def _closure(self, target: str) -> set[str]:
        seen: set[str] = set()
        stack = [target]
        while stack:
            item_id = stack.pop()
            if item_id in seen:
                continue
            seen.add(item_id)
            bp = self.producer(item_id)
            if bp is not None:
                stack.extend(i for i, _ in bp.inputs)
        return seen

    def to_state(self) -> list[dict[str, Any]]:
        return [self._by_id[b].to_dict() for b in self.ids()]

    @classmethod
    def from_state(
        cls, rows: Iterable[Mapping[str, Any]], *, items: Iterable[str] | None = None
    ) -> "BlueprintBook":
        return cls([Blueprint.from_dict(r) for r in rows], items=items)


__all__ = [
    "MAX_WASTE_BPS",
    "Blueprint",
    "BlueprintBook",
    "ChainPlan",
    "PlanStep",
    "ceil_div",
]
