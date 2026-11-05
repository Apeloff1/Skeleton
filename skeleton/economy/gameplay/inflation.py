"""B029 anti-inflation controller.

:class:`InflationController` watches one currency's circulating supply at
epoch boundaries and steers a *dynamic tax sink* toward a target growth
rate using an integer proportional-integral law:

    error    = growth_bps - target_growth_bps
    integral = clamp(integral + error, ±integral_limit)
    tax_bps  = clamp(base_tax_bps + kp*error/BPS + ki*integral/BPS,
                     min_tax_bps, max_tax_bps)

Inflation raises the tax, deflation lowers it, and the clamps keep both the
rate and the integral (anti-windup) bounded. The tax is burned with
:meth:`GameplayEconomy.charge_amount` under a declared sink, so it shows up
in flow reports like any other sink. ``faucet_scale_bps`` is a matching
recommendation for designers to throttle discretionary faucets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import BPS, EconomySimError, _bps_of, _req_id, _req_int


def _clamp(value: int, lo: int, hi: int) -> int:
    return lo if value < lo else hi if value > hi else value


def _div(a: int, b: int) -> int:
    """Integer division truncating toward zero (symmetric for +/- errors)."""
    q = abs(a) // b
    return q if a >= 0 else -q


@dataclass
class InflationController:
    currency: str
    sink_id: str
    target_growth_bps: int = 0
    base_tax_bps: int = 200
    min_tax_bps: int = 0
    max_tax_bps: int = 2_000
    kp_bps: int = 5_000
    ki_bps: int = 1_000
    integral_limit: int = 20_000
    min_faucet_scale_bps: int = 2_500
    tax_bps: int = field(init=False)
    integral: int = field(default=0, init=False)
    _last_supply: int | None = field(default=None, init=False)
    history: list[dict[str, int]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        _req_id(self.currency, "currency")
        _req_id(self.sink_id, "sink_id")
        for name in ("base_tax_bps", "min_tax_bps", "max_tax_bps", "kp_bps", "ki_bps", "integral_limit"):
            _req_int(getattr(self, name), name)
        if isinstance(self.target_growth_bps, bool) or not isinstance(self.target_growth_bps, int):
            raise EconomySimError("invalid target_growth_bps")
        if not self.min_tax_bps <= self.base_tax_bps <= self.max_tax_bps <= BPS:
            raise EconomySimError("need min <= base <= max <= 100%")
        _req_int(self.min_faucet_scale_bps, "min_faucet_scale_bps")
        if self.min_faucet_scale_bps > BPS:
            raise EconomySimError("min_faucet_scale_bps above 100%")
        self.tax_bps = self.base_tax_bps

    def bind(self, econ: GameplayEconomy) -> None:
        """Validate against an economy: the sink must exist and burn ``currency``."""
        spec = econ.sinks.get(self.sink_id)
        if spec is None or spec.currency != self.currency:
            raise EconomySimError("controller sink must be a declared sink of its currency")

    def observe(self, econ: GameplayEconomy) -> dict[str, int]:
        """Close an epoch: measure growth and retune ``tax_bps``."""
        self.bind(econ)
        supply = econ.flow_report(self.currency)["circulating"]
        if self._last_supply is None:
            self._last_supply = supply
            state = {"supply": supply, "growth_bps": 0, "error_bps": 0, "tax_bps": self.tax_bps}
            self.history.append(state)
            return dict(state)
        growth = _div((supply - self._last_supply) * BPS, max(self._last_supply, 1))
        error = growth - self.target_growth_bps
        self.integral = _clamp(self.integral + error, -self.integral_limit, self.integral_limit)
        raw = self.base_tax_bps + _div(self.kp_bps * error, BPS) + _div(self.ki_bps * self.integral, BPS)
        self.tax_bps = _clamp(raw, self.min_tax_bps, self.max_tax_bps)
        self._last_supply = supply
        state = {"supply": supply, "growth_bps": growth, "error_bps": error, "tax_bps": self.tax_bps}
        self.history.append(state)
        return dict(state)

    @property
    def faucet_scale_bps(self) -> int:
        """Recommended faucet payout scale: 100% unless tax is above base."""
        excess = self.tax_bps - self.base_tax_bps
        if excess <= 0:
            return BPS
        span = max(self.max_tax_bps - self.base_tax_bps, 1)
        return max(self.min_faucet_scale_bps, BPS - (BPS - self.min_faucet_scale_bps) * excess // span)

    def tax_on(self, amount: int) -> int:
        _req_int(amount, "amount")
        return _bps_of(amount, self.tax_bps) if self.tax_bps else 0

    def apply_tax(self, econ: GameplayEconomy, owner: str, amount: int) -> int:
        """Burn the current tax on a taxable ``amount`` from ``owner``."""
        self.bind(econ)
        tax = self.tax_on(amount)
        if tax:
            econ.charge_amount(self.sink_id, owner, tax)
        return tax

    def snapshot(self) -> dict[str, Any]:
        return {"tax_bps": self.tax_bps, "integral": self.integral, "last_supply": self._last_supply}


__all__ = ["InflationController"]
