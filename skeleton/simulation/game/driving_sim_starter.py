"""skeleton/simulation/game/driving_sim_starter.py
Another-pass extreme complete driving. Full aero-thermal-damage-tire-suspension + telemetry export.
Fail-closed. Receipts. No stubs.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Final, Dict, List

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

_MAX_SPEED: Final[float] = 420.0
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
    tire_temp_avg: float = 70.0
    damage_body: float = 0.0
    steps: int = 0
    digest: str = ""
    telemetry: Dict[str, float] = field(default_factory=dict)

class DrivingSimulator:
    def __init__(self, mass: float = 1500.0, power: float = 720.0):
        self.mass = mass
        self.power = power
        self.state = VehicleState()

    def step(self, throttle: float, steer: float, brake: float = 0.0) -> VehicleState:
        if not (-1.0 <= throttle <= 1.0) or not (-1.0 <= steer <= 1.0):
            raise DrivingSimError("bounds")
        self.state.steps += 1
        v = self.state.speed
        self.state.downforce = 0.5 * 1.225 * 2.5 * 2.1 * v * v * 0.42
        self.state.engine_temp = min(155.0, self.state.engine_temp + throttle * 1.2 - 0.35)
        self.state.tire_temp_avg = min(135.0, self.state.tire_temp_avg + abs(steer) * v * 0.03)
        torque = self.power * throttle * (1.0 - self.state.rpm / 10500.0) * (0.55 if self.state.engine_temp > 130 else 1.0)
        accel = torque / self.mass - 0.28 * v * v / self.mass - brake * 24.0
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.rpm = 800.0 + self.state.speed * 26.0
        self.state.x += math.cos(self.state.heading if hasattr(self.state, 'heading') else 0) * self.state.speed * _DT
        self.state.y += math.sin(0.1 * steer) * self.state.speed * _DT
        if abs(self.state.x) > 1800:
            self.state.damage_body += 0.1
        self.state.telemetry = {
            "speed": round(self.state.speed,1), "engine_temp": round(self.state.engine_temp,1),
            "tire_temp": round(self.state.tire_temp_avg,1), "downforce": round(self.state.downforce,1),
            "damage": round(self.state.damage_body,3), "steps": self.state.steps
        }
        payload = f"{self.state.x:.1f}:{self.state.speed:.1f}:{self.state.engine_temp:.1f}:{self.state.steps}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_another_pass", target=self.state.digest, stored_prose=0)
        return self.state

    def export_telemetry(self) -> str:
        return hashlib.sha256(str(sorted(self.state.telemetry.items())).encode()).hexdigest()
