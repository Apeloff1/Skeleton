"""P0 runtime integration bridge for frontier game milestones.

Candidate-only. Binds weather, presentation clocks, LOD and cognition
receipts into a single runtime admission record. Does not execute GPU
work or mutate live world state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Mapping

from .game_frontier_dynamics import FPS_MODES, PresentationClock


class P0AdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class P0RuntimeReceipt:
    """Immutable admission record for a frontier runtime candidate."""

    clock_fps: int
    lod_tier: int
    weather_digest: str
    cognition_digest: str
    admission_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.clock_fps not in FPS_MODES:
            raise P0AdmissionError(f"clock_fps must be one of {sorted(FPS_MODES)}")
        if not 0 <= self.lod_tier <= 4:
            raise P0AdmissionError("lod_tier must be 0..4")
        for label, value in (("weather", self.weather_digest), ("cognition", self.cognition_digest)):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise P0AdmissionError(f"{label}_digest must be lowercase SHA-256")
        payload = json.dumps(
            {
                "clock_fps": self.clock_fps,
                "lod_tier": self.lod_tier,
                "weather": self.weather_digest,
                "cognition": self.cognition_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(self, "admission_id", sha256(payload.encode()).hexdigest())


def admit_p0_runtime(
    clock: PresentationClock,
    *,
    lod_tier: int,
    weather_digest: str,
    cognition_digest: str,
) -> P0RuntimeReceipt:
    """Admit a candidate runtime. Fails closed on invalid clocks or digests."""
    return P0RuntimeReceipt(
        clock_fps=clock.fps,
        lod_tier=lod_tier,
        weather_digest=weather_digest,
        cognition_digest=cognition_digest,
    )


def p0_status(receipt: P0RuntimeReceipt) -> Mapping[str, object]:
    return {
        "admission_id": receipt.admission_id,
        "clock_fps": receipt.clock_fps,
        "lod_tier": receipt.lod_tier,
        "milestone": "P0",
        "claim": "candidate-only",
    }
