"""skeleton/simulation/game/driving_kinematic.py
Fail-closed driving kinematic extender starter.
Tracks bounded position/velocity. Never claims full physics or input-driven play.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_MAX_SPEED: Final[float] = 100.0
_MAX_POS: Final[float] = 10000.0

class DrivingError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    digest: str = ""

class DrivingKinematic:
    def __init__(self) -> None:
        self.state = VehicleState()

    def step(self, ax: float, ay: float, dt: float) -> VehicleState:
        if dt <= 0 or dt > 1.0:
            raise DrivingError("dt out of bounds")
        self.state.vx = max(-_MAX_SPEED, min(_MAX_SPEED, self.state.vx + ax * dt))
        self.state.vy = max(-_MAX_SPEED, min(_MAX_SPEED, self.state.vy + ay * dt))
        self.state.x = max(-_MAX_POS, min(_MAX_POS, self.state.x + self.state.vx * dt))
        self.state.y = max(-_MAX_POS, min(_MAX_POS, self.state.y + self.state.vy * dt))
        payload = f"{self.state.x:.4f}:{self.state.y:.4f}:{self.state.vx:.4f}:{self.state.vy:.4f}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(
            kind="driving_step",
            digest=self.state.digest,
            x=self.state.x,
            y=self.state.y,
            stored_prose=0,
        )
        return self.state

    def reset(self) -> None:
        self.state = VehicleState()
        emit_receipt(kind="driving_reset", stored_prose=0)
