"""Industry telemetry, folded per period next to the market's inflation rows.

Per period (``period_ticks``) one integer row records what industry added
to and removed from the economy:

* ``extracted`` — raw units minted by extraction nodes (item faucet).
* ``crafted`` / ``crafted_value`` — units delivered by builds and their
  value at the market's price (see :meth:`IndustrySystem.value_of`).
* ``consumed`` / ``lost`` / ``lost_value`` — units burned as inputs and as
  crafting waste (item sinks).
* ``install_fees`` / ``research_spend`` — money burned through sinks.
* ``money_supply`` and ``price_index_bps`` — read from the economy ledger
  and the market's :class:`InflationTelemetry` at close (``-1`` when the
  market has no index yet or no market is attached).
* ``money_sink_bps`` — industry money sinks per 10k of money supply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.economy.gameplay.industry.errors import IndustryError
from skeleton.simulation.economy.sim import BPS, _req_int

COUNTERS = (
    "extracted",
    "crafted",
    "crafted_value",
    "consumed",
    "lost",
    "lost_value",
    "install_fees",
    "research_spend",
    "jobs_started",
    "jobs_done",
)


@dataclass
class IndustryTelemetry:
    period_ticks: int = 100
    current: dict[str, int] | None = None
    rows: list[dict[str, int]] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=lambda: {k: 0 for k in COUNTERS})

    def __post_init__(self) -> None:
        _req_int(self.period_ticks, "period_ticks", minimum=1)

    def period_of(self, tick: int) -> int:
        return tick // self.period_ticks

    def bump(self, tick: int, **counts: int) -> None:
        period = self.period_of(tick)
        if self.current is None:
            self.current = {"period": period, **{k: 0 for k in COUNTERS}}
        elif period != self.current["period"]:
            raise IndustryError("close the open period before recording the next")
        for key, value in counts.items():
            if key not in COUNTERS:
                raise IndustryError(f"unknown counter {key!r}")
            self.current[key] += value
            self.totals[key] += value

    def pending_period(self) -> int | None:
        return None if self.current is None else self.current["period"]

    def close(
        self, period: int, money_supply: int, price_index_bps: int | None
    ) -> dict[str, int]:
        if self.rows and period <= self.rows[-1]["period"]:
            raise IndustryError("period already closed")
        if self.current is not None and self.current["period"] == period:
            row = dict(self.current)
            self.current = None
        else:
            row = {"period": period, **{k: 0 for k in COUNTERS}}
        sinks = row["install_fees"] + row["research_spend"]
        row["money_supply"] = money_supply
        row["price_index_bps"] = -1 if price_index_bps is None else price_index_bps
        row["money_sink_bps"] = sinks * BPS // money_supply if money_supply > 0 else 0
        self.rows.append(row)
        return dict(row)

    def to_state(self) -> dict[str, Any]:
        return {
            "period_ticks": self.period_ticks,
            "current": None if self.current is None else dict(self.current),
            "rows": [dict(r) for r in self.rows],
            "totals": dict(self.totals),
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "IndustryTelemetry":
        tel = cls(int(state["period_ticks"]))
        cur = state.get("current")
        tel.current = None if cur is None else {k: int(v) for k, v in cur.items()}
        tel.rows = [{k: int(v) for k, v in r.items()} for r in state["rows"]]
        tel.totals = {k: int(state["totals"].get(k, 0)) for k in COUNTERS}
        return tel


__all__ = ["COUNTERS", "IndustryTelemetry"]
