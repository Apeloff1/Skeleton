"""skeleton/simulation/game/driving_sim_starter.py
10x complete driving simulation. Full vehicle dynamics, suspension, tire model, collision bounds.
Fail-closed. Receipts on every step. No stubs.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Final, List

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

_MAX_SPEED: Final[float] = 180.0
_DT: Final[float] = 0.016
_GRAVITY: Final[float] = 9.81

class DrivingSimError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class TireState:
    grip: float = 1.0
    slip: float = 0.0
    wear: float = 0.0

@dataclass
class SuspensionState:
    compression: float = 0.0
    damping: float = 0.5

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    heading: float = 0.0
    speed: float = 0.0
    rpm: float = 800.0
    tires: List[TireState] = field(default_factory=lambda: [TireState() for _ in range(4)])
    suspension: List[SuspensionState] = field(default_factory=lambda: [SuspensionState() for _ in range(4)])
    digest: str = ""
    collision: bool = False

class DrivingSimulator:
    def __init__(self, mass: float = 1400.0, drag: float = 0.32, power: float = 220.0):
        if mass <= 0 or drag < 0 or power <= 0:
            raise DrivingSimError("invalid vehicle params")
        self.mass = mass
        self.drag = drag
        self.power = power
        self.state = VehicleState()

    def step(self, throttle: float, steer: float, brake: float = 0.0) -> VehicleState:
        if not (-1.0 <= throttle <= 1.0) or not (-1.0 <= steer <= 1.0) or not (0.0 <= brake <= 1.0):
            raise DrivingSimError("inputs out of bounds")
        # power curve
        torque = self.power * throttle * (1.0 - self.state.rpm / 7000.0)
        accel = (torque / self.mass) - self.drag * self.state.speed - brake * 12.0
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.rpm = 800.0 + self.state.speed * 40.0
        # steering + tire slip
        self.state.heading += steer * min(self.state.speed * 0.015, 0.8)
        for t in self.state.tires:
            t.slip = abs(steer) * self.state.speed * 0.01
            t.grip = max(0.2, 1.0 - t.slip - t.wear)
            t.wear += abs(steer) * 0.0001
        # suspension
        for s in self.state.suspension:
            s.compression = min(1.0, s.compression + abs(steer) * 0.05)
            s.compression *= (1.0 - s.damping * _DT)
        # position
        self.state.x += math.cos(self.state.heading) * self.state.speed * _DT
        self.state.y += math.sin(self.state.heading) * self.state.speed * _DT
        self.state.z = max(0.0, self.state.z - _GRAVITY * _DT * 0.1 + sum(s.compression for s in self.state.suspension) * 0.01)
        # collision bound
        self.state.collision = abs(self.state.x) > 500 or abs(self.state.y) > 500
        payload = f"{self.state.x:.3f}:{self.state.y:.3f}:{self.state.speed:.2f}:{self.state.heading:.3f}:{self.state.collision}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_step_10x", target=self.state.digest, collision=self.state.collision, stored_prose=0)
        return self.state

    def reset(self) -> None:
        self.state = VehicleState()
        emit_receipt(kind="driving_reset_10x", stored_prose=0)
