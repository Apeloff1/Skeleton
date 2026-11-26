"""Pure present / interpolate / drop policy for target rates 30, 50, 60, and 120.

The decision is a function of the target rate, the measured simulation step
time, and the fixed simulation dt. Inputs come from the caller. A dropped
frame does not advance the observation index. An interpolated frame is
labeled interpolated and cannot be stored as a captured observation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from skeleton.frontier_temporal.record import (
    CameraPose,
    TemporalMemoryError,
    TemporalRecord,
    TemporalWorldMemory,
    _finite,
)

TARGET_RATES = (30, 50, 60, 120)
_MAX_SECONDS = 60.0


@dataclass(frozen=True)
class FramePolicyDecision:
    """One presentation decision. Fields are checked against the decision kind."""

    target_rate: int
    simulation_step_s: float
    fixed_dt_s: float
    decision: str
    interpolation_alpha: float | None
    advances_observation_index: bool
    storable_as_captured: bool
    label: str

    def __post_init__(self) -> None:
        if self.target_rate not in TARGET_RATES:
            raise TemporalMemoryError("target rate must be 30, 50, 60, or 120")
        if self.decision == "present":
            consistent = (
                self.advances_observation_index is True
                and self.storable_as_captured is True
                and self.label == "captured"
                and self.interpolation_alpha is None
            )
        elif self.decision == "interpolate":
            alpha = self.interpolation_alpha
            consistent = (
                self.advances_observation_index is False
                and self.storable_as_captured is False
                and self.label == "interpolated"
                and type(alpha) is float
                and math.isfinite(alpha)
                and 0.0 <= alpha <= 1.0
            )
        elif self.decision == "drop":
            consistent = (
                self.advances_observation_index is False
                and self.storable_as_captured is False
                and self.label == "dropped"
                and self.interpolation_alpha is None
            )
        else:
            raise TemporalMemoryError("decision must be present, interpolate, or drop")
        if not consistent:
            raise TemporalMemoryError("frame decision fields contradict the decision kind")


def _alpha(simulation_step_s: float, fixed_dt_s: float) -> float:
    ratio = simulation_step_s / fixed_dt_s
    if not math.isfinite(ratio) or ratio < 0.0:
        raise TemporalMemoryError("interpolation ratio must be finite and non-negative")
    fractional = ratio - math.floor(ratio)
    if fractional == 0.0 and ratio > 0.0:
        return 1.0
    return float(fractional)


def decide_frame_policy(
    *,
    target_rate: int,
    simulation_step_s: float,
    fixed_dt_s: float,
) -> FramePolicyDecision:
    """Decide present, interpolate, or drop.

    ``simulation_step_s`` is the measured cost of the simulation step, supplied
    by the caller. ``fixed_dt_s`` is the simulation quantum. The presentation
    period is ``1 / target_rate``.

    * present — the step finished inside one presentation period and the
      simulation quantum is no coarser than that period. The result is a
      captured observation.
    * interpolate — the step is late by less than one extra period, or the
      simulation quantum is coarser than the presentation period. The result
      is labeled interpolated.
    * drop — the measured step covers at least two presentation periods.
      Drop wins over interpolation.
    """
    if type(target_rate) is not int or isinstance(target_rate, bool) or target_rate not in TARGET_RATES:
        raise TemporalMemoryError("target rate must be 30, 50, 60, or 120")
    step = _finite(simulation_step_s, "simulation_step_s", limit=_MAX_SECONDS)
    dt = _finite(fixed_dt_s, "fixed_dt_s", limit=_MAX_SECONDS)
    if step < 0.0:
        raise TemporalMemoryError("simulation_step_s must be non-negative")
    if dt <= 0.0:
        raise TemporalMemoryError("fixed_dt_s must be positive")
    period = 1.0 / target_rate
    if step >= 2.0 * period:
        decision = "drop"
        alpha = None
        advances = False
        storable = False
        label = "dropped"
    elif step <= period and dt <= period:
        decision = "present"
        alpha = None
        advances = True
        storable = True
        label = "captured"
    else:
        decision = "interpolate"
        alpha = _alpha(step, dt)
        advances = False
        storable = False
        label = "interpolated"
    return FramePolicyDecision(
        target_rate,
        step,
        dt,
        decision,
        alpha,
        advances,
        storable,
        label,
    )


@dataclass
class ObservationCursor:
    """Applies frame decisions to temporal memory.

    Only a present decision appends a captured observation and advances the
    observation index. Drop and interpolate leave the index where it is.
    """

    memory: TemporalWorldMemory
    observation_index: int = 0
    presented: int = 0
    interpolated: int = 0
    dropped: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.memory, TemporalWorldMemory):
            raise TemporalMemoryError("observation cursor requires temporal world memory")
        if type(self.observation_index) is not int or self.observation_index < 0:
            raise TemporalMemoryError("observation index must be a non-negative int")

    def metrics(self) -> dict[str, int]:
        return {
            "observation_index": self.observation_index,
            "presented": self.presented,
            "interpolated": self.interpolated,
            "dropped": self.dropped,
            "stored_observations": len(self.memory.live_records),
        }

    def apply(
        self,
        decision: FramePolicyDecision,
        *,
        observation_digest: str,
        observation_digest_field: str,
        action: tuple,
        pose: CameraPose,
    ) -> dict[str, object]:
        if not isinstance(decision, FramePolicyDecision):
            raise TemporalMemoryError("frame policy decision required")
        if decision.decision == "drop":
            self.dropped += 1
            return {
                "stored": False,
                "observation_index": self.observation_index,
                "label": "dropped",
                "advances_observation_index": False,
            }
        if decision.decision == "interpolate":
            self.interpolated += 1
            return {
                "stored": False,
                "observation_index": self.observation_index,
                "label": "interpolated",
                "advances_observation_index": False,
            }
        record = TemporalRecord(
            frame_index=self.observation_index,
            observation_digest=observation_digest,
            observation_digest_field=observation_digest_field,
            action=action,
            pose=pose,
            kind="captured",
        )
        self.memory.append(record)
        stored_at = self.observation_index
        self.observation_index += 1
        self.presented += 1
        return {
            "stored": True,
            "observation_index": stored_at,
            "label": "captured",
            "advances_observation_index": True,
        }
