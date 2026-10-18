"""Typed liveness and readiness contracts over the existing probe payloads.

HTTP handlers keep their current JSON. Callers that need a stable internal
shape parse those payloads here instead of inventing a second health URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


HEALTH_CONTRACT_VERSION = "1.0.0"


class HealthContractError(ValueError):
    """A health payload does not match the published contract."""


@dataclass(frozen=True)
class LivenessContract:
    alive: bool
    schema_version: str = HEALTH_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HEALTH_CONTRACT_VERSION:
            raise HealthContractError("schema_version mismatch")
        if not isinstance(self.alive, bool):
            raise HealthContractError("alive must be a boolean")


@dataclass(frozen=True)
class ReadinessContract:
    ready: bool
    status: str | None = None
    schema_version: str = HEALTH_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HEALTH_CONTRACT_VERSION:
            raise HealthContractError("schema_version mismatch")
        if not isinstance(self.ready, bool):
            raise HealthContractError("ready must be a boolean")
        if self.status is not None and (not isinstance(self.status, str) or not self.status):
            raise HealthContractError("status must be non-empty text when present")


def parse_liveness(payload: object) -> LivenessContract:
    """Accept the engine liveness object (``alive`` plus any extra fields)."""

    if not isinstance(payload, Mapping) or not isinstance(payload.get("alive"), bool):
        raise HealthContractError("liveness payload requires boolean alive")
    return LivenessContract(alive=payload["alive"])


def parse_readiness(payload: object) -> ReadinessContract:
    """Accept the engine readiness object (``ready``, optional ``status``)."""

    if not isinstance(payload, Mapping) or not isinstance(payload.get("ready"), bool):
        raise HealthContractError("readiness payload requires boolean ready")
    status = payload.get("status")
    if status is not None and not isinstance(status, str):
        raise HealthContractError("status must be text when present")
    return ReadinessContract(ready=payload["ready"], status=status or None)


__all__ = [
    "HEALTH_CONTRACT_VERSION",
    "HealthContractError",
    "LivenessContract",
    "ReadinessContract",
    "parse_liveness",
    "parse_readiness",
]
