"""Extraction nodes: finite resource deposits run as capped item faucets.

An :class:`ExtractionNode` holds a finite ``reserve`` of one raw item.
Each extraction mints up to ``yield_per_cycle`` items into the extractor's
inventory through :meth:`GameplayEconomy.grant_items` under the source
label ``extract:<node_id>``, so the economy's per-item ledger (minted by
source) records every unit. Three independent caps bound the faucet:

* **Depletion** — the reserve only goes down; a depleted node mints nothing.
* **Cooldown** — one extraction per owner per ``cycle_ticks``.
* **Rolling window** — at most ``window_cap`` units per ``window_ticks``
  across all owners of the node.

The last extraction from a nearly empty node yields only what is left, and
an extraction that would exceed the window cap is trimmed to fit. If the
trimmed yield is zero the call is refused and nothing changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.industry.errors import (
    ExtractionCapped,
    IndustryError,
    NodeDepleted,
)
from skeleton.simulation.economy.sim import _req_id, _req_int

EXTRACT_PREFIX = "extract:"


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    item: str
    reserve: int
    yield_per_cycle: int
    cycle_ticks: int = 1
    window_ticks: int = 0
    window_cap: int | None = None

    def __post_init__(self) -> None:
        _req_id(self.node_id, "node_id")
        _req_id(self.item, "node item")
        _req_int(self.reserve, "reserve", minimum=1)
        _req_int(self.yield_per_cycle, "yield_per_cycle", minimum=1)
        _req_int(self.cycle_ticks, "cycle_ticks", minimum=1)
        _req_int(self.window_ticks, "window_ticks")
        if self.window_cap is not None:
            _req_int(self.window_cap, "window_cap", minimum=1)
            if self.window_ticks < 1:
                raise IndustryError("window_cap requires window_ticks >= 1")

    @property
    def source(self) -> str:
        return f"{EXTRACT_PREFIX}{self.node_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "item": self.item,
            "reserve": self.reserve,
            "yield_per_cycle": self.yield_per_cycle,
            "cycle_ticks": self.cycle_ticks,
            "window_ticks": self.window_ticks,
            "window_cap": self.window_cap,
        }


@dataclass
class ExtractionNode:
    spec: NodeSpec
    remaining: int = -1
    extracted: int = 0
    last_by_owner: dict[str, int] = field(default_factory=dict)
    window: list[tuple[int, int]] = field(default_factory=list)
    last_tick: int = 0

    def __post_init__(self) -> None:
        if self.remaining < 0:
            self.remaining = self.spec.reserve

    @property
    def depleted(self) -> bool:
        return self.remaining == 0

    def window_used(self, tick: int) -> int:
        if self.spec.window_cap is None:
            return 0
        return sum(q for t, q in self.window if tick - t < self.spec.window_ticks)

    def available(self, owner: str, tick: int) -> int:
        """Units ``owner`` could extract at ``tick`` (0 if any cap blocks)."""
        if self.depleted:
            return 0
        last = self.last_by_owner.get(owner)
        if last is not None and tick - last < self.spec.cycle_ticks:
            return 0
        qty = min(self.spec.yield_per_cycle, self.remaining)
        if self.spec.window_cap is not None:
            qty = min(qty, self.spec.window_cap - self.window_used(tick))
        return max(qty, 0)

    def extract(self, econ: GameplayEconomy, owner: str, tick: int) -> int:
        _req_int(tick, "tick")
        if tick < self.last_tick:
            raise IndustryError("tick went backwards")
        if self.depleted:
            raise NodeDepleted(f"node {self.spec.node_id!r} is depleted")
        last = self.last_by_owner.get(owner)
        if last is not None and tick - last < self.spec.cycle_ticks:
            raise ExtractionCapped("extraction on cooldown")
        qty = self.available(owner, tick)
        if qty < 1:
            raise ExtractionCapped("node window cap reached")
        if not econ.fits_many(owner, {self.spec.item: qty}):
            raise IndustryError("inventory full")
        econ.grant_items(self.spec.source, owner, self.spec.item, qty)
        self.remaining -= qty
        self.extracted += qty
        self.last_by_owner[owner] = tick
        self.last_tick = tick
        if self.spec.window_cap is not None:
            self.window = [
                (t, q) for t, q in self.window if tick - t < self.spec.window_ticks
            ]
            self.window.append((tick, qty))
        return qty

    def to_state(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "remaining": self.remaining,
            "extracted": self.extracted,
            "last_by_owner": dict(sorted(self.last_by_owner.items())),
            "window": [list(w) for w in self.window],
            "last_tick": self.last_tick,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "ExtractionNode":
        node = cls(
            NodeSpec(**state["spec"]),
            remaining=int(state["remaining"]),
            extracted=int(state["extracted"]),
            last_by_owner={k: int(v) for k, v in state["last_by_owner"].items()},
            window=[(int(t), int(q)) for t, q in state["window"]],
            last_tick=int(state["last_tick"]),
        )
        if node.remaining + node.extracted != node.spec.reserve:
            raise IndustryError("node reserve does not balance")
        return node


__all__ = ["EXTRACT_PREFIX", "ExtractionNode", "NodeSpec"]
