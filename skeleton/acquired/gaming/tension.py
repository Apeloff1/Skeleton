"""Deterministic tension/reeling simulation evolved from Newsay Fishing Master.

The source game combines fish resistance, weather load, rod relief and random
struggle spikes into line tension, breaking the line at a hard threshold and
allowing a catch after sustained reeling below a safe threshold.

This port separates simulation from UI/timers and removes hidden randomness:
callers decide when a struggle impulse occurs, making the mechanic replayable,
testable and suitable for agents or server-authoritative simulation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from skeleton.kernel.events import EventBus


class TensionOutcome(str, Enum):
    REELING = "reeling"
    CAUGHT = "caught"
    LOST = "lost"


@dataclass(frozen=True)
class TensionConfig:
    tick_seconds: float = 0.2
    resistance_gain: float = 0.08
    environment_gain: float = 0.05
    reel_relief: float = 0.06
    struggle_gain: float = 0.15
    break_threshold: float = 1.0
    catch_threshold: float = 0.75
    min_reel_seconds: float = 4.0

    def __post_init__(self) -> None:
        numeric = {
            "tick_seconds": self.tick_seconds,
            "resistance_gain": self.resistance_gain,
            "environment_gain": self.environment_gain,
            "reel_relief": self.reel_relief,
            "struggle_gain": self.struggle_gain,
            "break_threshold": self.break_threshold,
            "catch_threshold": self.catch_threshold,
            "min_reel_seconds": self.min_reel_seconds,
        }
        for name, value in numeric.items():
            if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.tick_seconds <= 0:
            raise ValueError("tick_seconds must be positive")
        if self.break_threshold <= 0:
            raise ValueError("break_threshold must be positive")
        if self.catch_threshold >= self.break_threshold:
            raise ValueError("catch_threshold must be below break_threshold")


@dataclass(frozen=True)
class TensionState:
    tension: float = 0.2
    elapsed_seconds: float = 0.0
    outcome: TensionOutcome = TensionOutcome.REELING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tension": self.tension,
            "elapsed_seconds": self.elapsed_seconds,
            "outcome": self.outcome.value,
        }


class TensionModel:
    """Advance a bounded line-tension simulation one deterministic step."""

    def __init__(
        self,
        config: TensionConfig = TensionConfig(),
        *,
        bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self._steps = 0

    @staticmethod
    def _bounded(value: float, name: str, high: float = 4.0) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite")
        return max(0.0, min(high, number))

    def step(
        self,
        state: TensionState,
        *,
        resistance: float,
        environment_resistance: float = 1.0,
        reel_speed: float = 1.0,
        struggle: bool = False,
        dt: Optional[float] = None,
    ) -> TensionState:
        """Advance tension using the source mechanic normalized by timestep.

        ``resistance``, ``environment_resistance`` and ``reel_speed`` are
        bounded telemetry inputs. A struggle is an explicit event rather than
        an internal random draw, allowing exact replay from an event stream.
        Terminal states are idempotent.
        """

        if state.outcome is not TensionOutcome.REELING:
            return state

        step_seconds = self.config.tick_seconds if dt is None else self._bounded(dt, "dt", 1.0)
        if step_seconds <= 0:
            raise ValueError("dt must be positive")
        scale = step_seconds / self.config.tick_seconds
        fish = self._bounded(resistance, "resistance", 2.0)
        environment = self._bounded(environment_resistance, "environment_resistance", 2.0)
        reel = self._bounded(reel_speed, "reel_speed", 4.0)
        current = self._bounded(state.tension, "state.tension", self.config.break_threshold * 2)

        delta = (
            fish * self.config.resistance_gain
            + environment * self.config.environment_gain
            - reel * self.config.reel_relief
        ) * scale
        if struggle:
            delta += self.config.struggle_gain

        tension = max(0.0, current + delta)
        elapsed = max(0.0, float(state.elapsed_seconds)) + step_seconds

        if tension >= self.config.break_threshold:
            outcome = TensionOutcome.LOST
        elif elapsed >= self.config.min_reel_seconds and tension < self.config.catch_threshold:
            outcome = TensionOutcome.CAUGHT
        else:
            outcome = TensionOutcome.REELING

        result = TensionState(
            tension=round(min(tension, self.config.break_threshold * 2), 6),
            elapsed_seconds=round(elapsed, 6),
            outcome=outcome,
        )
        self._steps += 1
        if self.bus:
            self.bus.emit(
                "acquired.gaming.tension.step",
                {
                    "tension": result.tension,
                    "elapsed_seconds": result.elapsed_seconds,
                    "outcome": result.outcome.value,
                    "struggle": bool(struggle),
                },
            )
            if result.outcome is not TensionOutcome.REELING:
                self.bus.emit(
                    f"acquired.gaming.tension.{result.outcome.value}",
                    result.to_dict(),
                )
        return result

    def stats(self) -> Dict[str, int]:
        return {"steps": self._steps}


__all__ = ["TensionConfig", "TensionModel", "TensionOutcome", "TensionState"]
