"""Research levels: material efficiency (ME) and time efficiency (TE).

Each owner researches each blueprint separately. Raising a level costs
money, burned through a declared economy sink (``research_sink``) with the
cost growing geometrically per level, and takes ticks of research time —
the level only applies once its job completes (see
:class:`~skeleton.economy.gameplay.industry.engine.IndustrySystem`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.economy.gameplay.industry.errors import IndustryError
from skeleton.simulation.economy.sim import BPS, _req_int

ME = "me"
TE = "te"
TRACKS = (ME, TE)


@dataclass(frozen=True)
class ResearchCurve:
    base_cost: int = 100
    growth_bps: int = 15_000
    base_ticks: int = 50
    tick_growth_bps: int = 12_000

    def __post_init__(self) -> None:
        _req_int(self.base_cost, "base_cost", minimum=1)
        _req_int(self.base_ticks, "base_ticks", minimum=1)
        _req_int(self.growth_bps, "growth_bps", minimum=BPS)
        _req_int(self.tick_growth_bps, "tick_growth_bps", minimum=BPS)

    def _scaled(self, base: int, growth: int, level: int) -> int:
        value = base
        for _ in range(level):
            value = value * growth // BPS
        return value

    def cost(self, to_level: int) -> int:
        """Money to go from ``to_level - 1`` to ``to_level``."""
        _req_int(to_level, "to_level", minimum=1)
        return self._scaled(self.base_cost, self.growth_bps, to_level - 1)

    def ticks(self, to_level: int) -> int:
        _req_int(to_level, "to_level", minimum=1)
        return self._scaled(self.base_ticks, self.tick_growth_bps, to_level - 1)

    def to_dict(self) -> dict[str, int]:
        return {
            "base_cost": self.base_cost,
            "growth_bps": self.growth_bps,
            "base_ticks": self.base_ticks,
            "tick_growth_bps": self.tick_growth_bps,
        }


class ResearchLevels:
    """``(owner, blueprint) -> {me, te}`` with per-blueprint caps."""

    def __init__(self) -> None:
        self._levels: dict[str, dict[str, dict[str, int]]] = {}

    def level(self, owner: str, blueprint_id: str, track: str) -> int:
        if track not in TRACKS:
            raise IndustryError("track must be 'me' or 'te'")
        return self._levels.get(owner, {}).get(blueprint_id, {}).get(track, 0)

    def levels(self, owner: str, blueprint_id: str) -> tuple[int, int]:
        return self.level(owner, blueprint_id, ME), self.level(owner, blueprint_id, TE)

    def raise_level(self, owner: str, blueprint_id: str, track: str, cap: int) -> int:
        current = self.level(owner, blueprint_id, track)
        if current >= cap:
            raise IndustryError("research level at cap")
        per = self._levels.setdefault(owner, {}).setdefault(blueprint_id, {})
        per[track] = current + 1
        return current + 1

    def for_owner(self, owner: str) -> dict[str, tuple[int, int]]:
        return {b: self.levels(owner, b) for b in sorted(self._levels.get(owner, {}))}

    def to_state(self) -> dict[str, Any]:
        return {
            o: {b: dict(sorted(t.items())) for b, t in sorted(per.items())}
            for o, per in sorted(self._levels.items())
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "ResearchLevels":
        r = cls()
        r._levels = {
            o: {b: {k: int(v) for k, v in t.items()} for b, t in per.items()}
            for o, per in state.items()
        }
        return r


__all__ = ["ME", "TE", "TRACKS", "ResearchCurve", "ResearchLevels"]
