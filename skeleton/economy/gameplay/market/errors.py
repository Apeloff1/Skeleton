"""Market error types (stable ``code`` values for telemetry and clients)."""

from __future__ import annotations

from skeleton.simulation.economy.sim import EconomySimError


class MarketError(EconomySimError):
    code = "ECO.PMARKET"


class OrderRejected(MarketError):
    code = "ECO.PMARKET.REJECTED"


class IntegrityViolation(MarketError):
    code = "ECO.PMARKET.INTEGRITY"


class ConservationError(MarketError):
    code = "ECO.PMARKET.CONSERVATION"


__all__ = ["ConservationError", "IntegrityViolation", "MarketError", "OrderRejected"]
