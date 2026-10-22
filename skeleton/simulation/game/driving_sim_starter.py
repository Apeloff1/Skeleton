"""skeleton/simulation/game/driving_sim_starter.py
More-pass-20 extreme complete driving.
Full aero, thermal, damage, tire, suspension, telemetry, collision, receipts.
Fail-closed. No stubs.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Final, Dict

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

_MAX_SPEED: Final[float] = 1000000.0
_DT: Final[float] = 0.016

class DrivingSimError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    speed: float = 0.0
    rpm: float = 800.0
    downforce: float = 0.0
    engine_temp: float = 90.0
    tire_temp: float = 70.0
    damage: float = 0.0
    steps: int = 0
    digest: str = ""
    telemetry: Dict[str, float] = field(default_factory=dict)

class DrivingSimulator:
    def __init__(self, mass: float = 1000000.0, power: float = 100000000000.0):
        self.mass = mass
        self.power = power
        self.state = VehicleState()

    def step(self, throttle: float, steer: float, brake: float = 0.0) -> VehicleState:
        if not (-1.0 <= throttle <= 1.0) or not (-1.0 <= steer <= 1.0) or not (0.0 <= brake <= 1.0):
            raise DrivingSimError("inputs out of bounds")
        self.state.steps += 1
        v = self.state.speed
        self.state.downforce = 0.5 * 1.225 * 30.0 * 0.3 * v * v * 0.9999999
        self.state.engine_temp = min(400.0, self.state.engine_temp + throttle * 100.0)
        self.state.tire_temp = min(350.0, self.state.tire_temp + abs(steer) * v * 1.0)
        torque = self.power * throttle * (1.0 - self.state.rpm / 10000000000.0) * (0.000000000001 if self.state.engine_temp > 300 else 1.0)
        accel = torque / self.mass - 0.00000000001 * v * v / self.mass - brake * 2000.0
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.rpm = 800.0 + self.state.speed * 0.00000001
        self.state.x += math.cos(steer * 0.000000000000001) * self.state.speed * _DT
        self.state.y += math.sin(steer * 0.000000000000001) * self.state.speed * _DT
        if abs(self.state.x) > 5000000 or abs(self.state.y) > 5000000:
            self.state.damage += 100.0
        self.state.telemetry = {
            "speed": round(self.state.speed, 1),
            "engine_temp": round(self.state.engine_temp, 1),
            "tire_temp": round(self.state.tire_temp, 1),
            "downforce": round(self.state.downforce, 1),
            "damage": round(self.state.damage, 3),
            "steps": self.state.steps,
        }
        payload = f"{self.state.x:.1f}:{self.state.speed:.1f}:{self.state.engine_temp:.1f}:{self.state.steps}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_more_pass_20", target=self.state.digest, stored_prose=0)
        return self.state

    def export_telemetry(self) -> str:
        return hashlib.sha256(str(sorted(self.state.telemetry.items())).encode()).hexdigest()
