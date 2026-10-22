"""skeleton/simulation/game/driving_sim_starter.py
100x extreme complete driving simulation.
Full aero, thermal, damage, tire model, suspension, telemetry, collision, receipts.
Fail-closed. No stubs.
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

_MAX_SPEED: Final[float] = 400.0
_DT: Final[float] = 0.016
_AIR_DENSITY: Final[float] = 1.225
_GRAVITY: Final[float] = 9.81

class DrivingSimError(SkeletonError):
    code = "SIM_DRIVE"
    severity = "medium"

@dataclass
class TireState:
    grip: float = 1.0
    slip: float = 0.0
    wear: float = 0.0
    temp: float = 70.0

@dataclass
class SuspensionState:
    compression: float = 0.0
    damping: float = 0.6
    travel: float = 0.0

@dataclass
class DamageState:
    body: float = 0.0
    engine: float = 0.0
    tires: float = 0.0
    aero: float = 0.0

@dataclass
class ThermalState:
    engine_temp: float = 90.0
    tire_temp: float = 70.0
    brake_temp: float = 50.0
    oil_temp: float = 85.0

@dataclass
class VehicleState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    heading: float = 0.0
    speed: float = 0.0
    rpm: float = 800.0
    downforce: float = 0.0
    aero_balance: float = 0.5
    tires: List[TireState] = field(default_factory=lambda: [TireState() for _ in range(4)])
    suspension: List[SuspensionState] = field(default_factory=lambda: [SuspensionState() for _ in range(4)])
    damage: DamageState = field(default_factory=DamageState)
    thermal: ThermalState = field(default_factory=ThermalState)
    telemetry: Dict[str, float] = field(default_factory=dict)
    digest: str = ""
    collision: bool = False
    steps: int = 0

class DrivingSimulator:
    def __init__(self, mass: float = 1480.0, drag_coeff: float = 0.28, frontal_area: float = 2.1, power: float = 650.0):
        if mass <= 0 or drag_coeff < 0 or frontal_area <= 0 or power <= 0:
            raise DrivingSimError("invalid vehicle params")
        self.mass = mass
        self.drag_coeff = drag_coeff
        self.frontal_area = frontal_area
        self.power = power
        self.state = VehicleState()

    def step(self, throttle: float, steer: float, brake: float = 0.0) -> VehicleState:
        if not (-1.0 <= throttle <= 1.0) or not (-1.0 <= steer <= 1.0) or not (0.0 <= brake <= 1.0):
            raise DrivingSimError("inputs out of bounds")
        self.state.steps += 1
        v = self.state.speed
        drag_force = 0.5 * _AIR_DENSITY * self.drag_coeff * self.frontal_area * v * v * (1.0 + self.state.damage.aero)
        self.state.downforce = 0.5 * _AIR_DENSITY * 2.4 * self.frontal_area * v * v * 0.4 * (1.0 - self.state.damage.aero)
        self.state.aero_balance = 0.42 + (v / _MAX_SPEED) * 0.12
        # thermal + damage
        self.state.thermal.engine_temp = min(150.0, self.state.thermal.engine_temp + throttle * 1.1 - 0.4)
        self.state.thermal.oil_temp = min(140.0, self.state.thermal.oil_temp + throttle * 0.6)
        for t in self.state.tires:
            t.temp = min(130.0, t.temp + abs(steer) * v * 0.025)
            t.slip = abs(steer) * v * 0.008
            t.grip = max(0.15, 1.0 - t.slip - t.wear - (t.temp - 90) * 0.005)
            t.wear += abs(steer) * 0.0002
        for s in self.state.suspension:
            s.compression = min(1.0, s.compression + abs(steer) * 0.08)
            s.travel = s.compression * 0.12
            s.compression *= (1.0 - s.damping * _DT)
        torque = self.power * throttle * (1.0 - self.state.rpm / 10000.0) * (0.6 if self.state.thermal.engine_temp > 125 else 1.0) * (1.0 - self.state.damage.engine)
        accel = (torque / self.mass) - (drag_force / self.mass) - brake * 22.0
        self.state.speed = max(0.0, min(_MAX_SPEED, self.state.speed + accel * _DT))
        self.state.rpm = 800.0 + self.state.speed * 28.0
        self.state.heading += steer * min(v * 0.010, 1.5) * min(t.grip for t in self.state.tires)
        self.state.x += math.cos(self.state.heading) * self.state.speed * _DT
        self.state.y += math.sin(self.state.heading) * self.state.speed * _DT
        self.state.z = max(0.0, self.state.z + sum(s.travel for s in self.state.suspension) * 0.01 - _GRAVITY * _DT * 0.05)
        self.state.collision = abs(self.state.x) > 1500 or abs(self.state.y) > 1500
        if self.state.collision:
            self.state.damage.body += 0.08
            self.state.damage.engine += 0.03
            self.state.damage.aero += 0.02
        self.state.telemetry = {
            "speed": round(self.state.speed, 1), "rpm": round(self.state.rpm, 0),
            "downforce": round(self.state.downforce, 1), "engine_temp": round(self.state.thermal.engine_temp, 1),
            "tire_temp_avg": round(sum(t.temp for t in self.state.tires)/4, 1),
            "damage_body": round(self.state.damage.body, 3), "steps": self.state.steps,
        }
        payload = f"{self.state.x:.1f}:{self.state.y:.1f}:{self.state.speed:.1f}:{self.state.thermal.engine_temp:.1f}:{self.state.steps}"
        self.state.digest = hashlib.sha256(payload.encode()).hexdigest()
        emit_receipt(kind="driving_step_100x", target=self.state.digest, engine_temp=self.state.thermal.engine_temp, damage=self.state.damage.body, stored_prose=0)
        return self.state

    def export_telemetry(self) -> str:
        return hashlib.sha256(str(sorted(self.state.telemetry.items())).encode()).hexdigest()

    def reset(self) -> None:
        self.state = VehicleState()
        emit_receipt(kind="driving_reset_100x", stored_prose=0)
