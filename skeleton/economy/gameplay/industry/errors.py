"""Industry error types (stable ``code`` values for telemetry and clients)."""

from __future__ import annotations

from skeleton.simulation.economy.sim import EconomySimError


class IndustryError(EconomySimError):
    code = "ECO.INDUSTRY"


class JobRejected(IndustryError):
    code = "ECO.INDUSTRY.REJECTED"


class NodeDepleted(IndustryError):
    code = "ECO.INDUSTRY.DEPLETED"


class ExtractionCapped(IndustryError):
    code = "ECO.INDUSTRY.CAPPED"


class IndustryConservationError(IndustryError):
    code = "ECO.INDUSTRY.CONSERVATION"


__all__ = [
    "ExtractionCapped",
    "IndustryConservationError",
    "IndustryError",
    "JobRejected",
    "NodeDepleted",
]
