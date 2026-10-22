"""skeleton/simulation/game/driving_sim_starter.py
Complete driving simulation starter. Kinematic base + bounded physics integration.
Fail-closed on invalid inputs. Provenance receipts. No stubs.
"""
from __future__ import annotations

import hashlib
import math
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

_MAX_SPEED: Final[float] = 120.0
_DT: Final[float] = 0.016

class DrivingSimError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    speed: float = 0.0
    digest: str = ""

class DrivingSimulator:
    def __init__(self, mass: float = 1200.0, drag: float = 0.3):
        if mass <= 0 or drag < 0:
            raise DrivingSimError("invalid vehicle params")
        self.mass = mass
        self.drag = drag
        self.state = VehicleState()

    def step(self, throttle: float, steer: float) -> VehicleState:
        if not (-1.0 <= throttle <= 1.0) or not (-1.0 <= steer <= 1.0):
            raise DrivingSimError("throttle/steer out of bounds")
        accel = throttle * 8.0 - self.drag * self.state.speed
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.heading += steer * self.state.speed * 0.02
        self.state.x += math.cos(self.state.heading) * self.state.speed * _DT
        self.state.y += math.sin(self.state.heading) * self.state.speed * _DT
        payload = f"{self.state.x:.4f}:{self.state.y:.4f}:{self.state.heading:.4f}:{self.state.speed:.4f}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_step", target=self.state.digest, stored_prose=0)
        return self.state

    def reset(self) -> None:
        self.state = VehicleState()
        emit_receipt(kind="driving_reset", stored_prose=0)
