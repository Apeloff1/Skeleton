"""Prevent repeated tool loops.

Domain: agents; policy: agents.tool_loop.
This policy is admission evidence, not a claim that a physical device
or production runtime has been qualified.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from skeleton.ai.assurance.operational_planes.core import Assessment, Plane, Signal, assess

IDENTITY = "agents.tool_loop"
DOMAIN = "agents"
PURPOSE = "Prevent repeated tool loops"
PRIMARY_SIGNAL = "tool_calls_per_task"
SECONDARY_SIGNAL = "repeated_identical_actions"
PRIMARY_MAXIMUM = Decimal("120")
SECONDARY_MAXIMUM = Decimal("8")
MAX_AGE_SECONDS = 60

POLICY = Plane(
    identity=IDENTITY,
    domain=DOMAIN,
    purpose=PURPOSE,
    signals=(
        Signal(PRIMARY_SIGNAL, PRIMARY_MAXIMUM),
        Signal(SECONDARY_SIGNAL, SECONDARY_MAXIMUM),
    ),
    max_age_seconds=MAX_AGE_SECONDS,
)


def required_signals() -> tuple[str, str]:
    """Return names required from an independently collected observation."""
    return PRIMARY_SIGNAL, SECONDARY_SIGNAL


def limits() -> dict[str, str]:
    """Return stable decimal-encoded boundaries for integration consumers."""
    return {
        PRIMARY_SIGNAL: str(PRIMARY_MAXIMUM),
        SECONDARY_SIGNAL: str(SECONDARY_MAXIMUM),
    }


def evaluate(
    observation: Mapping[str, object],
    *,
    observed_at: int,
    now: int,
) -> Assessment:
    """Evaluate both signals; missing, invalid and stale data fail closed."""
    return assess(POLICY, observation, observed_at=observed_at, now=now)


def nominal_example() -> dict[str, int]:
    """Return a deterministic synthetic fixture; never live telemetry."""
    return {PRIMARY_SIGNAL: 0, SECONDARY_SIGNAL: 0}


def breach_example() -> dict[str, int]:
    """Return a synthetic violation of the primary bound."""
    return {
        PRIMARY_SIGNAL: int(PRIMARY_MAXIMUM) + 1,
        SECONDARY_SIGNAL: 0,
    }


def admission_allowed(
    observation: Mapping[str, object],
    *,
    observed_at: int,
    now: int,
) -> bool:
    """True only for a fresh, fully measured, in-bound observation."""
    return evaluate(observation, observed_at=observed_at, now=now).allowed
