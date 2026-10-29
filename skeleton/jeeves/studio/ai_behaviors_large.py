"""AI behavior subsystem (10x).
Patrol, chaser, turret, boss phases, attack pattern selection, decision trees.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import math

class BehaviorNode:
    def __init__(self, name: str):
        self.name = name
    def tick(self, ctx: Dict[str, Any]) -> str:
        return "success"

class PatrolBehavior(BehaviorNode):
    def __init__(self):
        super().__init__("patrol")
        self.idx = 0
    def tick(self, ctx: Dict[str, Any]) -> str:
        wps = ctx.get("waypoints", [(0.0,0.0),(10.0,0.0),(10.0,10.0),(0.0,10.0)])
        self.idx = (self.idx + 1) % len(wps)
        ctx["target"] = wps[self.idx]
        ctx["speed"] = 70.0
        return "running"

class ChaserBehavior(BehaviorNode):
    def tick(self, ctx: Dict[str, Any]) -> str:
        player = ctx.get("player_pos", (0.0, 0.0))
        me = ctx.get("pos", (0.0, 0.0))
        dx = player[0] - me[0]
        dy = player[1] - me[1]
        dist = math.hypot(dx, dy) or 1.0
        if dist < 1.6:
            ctx["in_range"] = True
            return "success"
        ctx["velocity"] = (dx / dist * 100.0, dy / dist * 100.0)
        return "running"

class TurretBehavior(BehaviorNode):
    def tick(self, ctx: Dict[str, Any]) -> str:
        timer = ctx.get("fire_timer", 0.0) + 0.016
        ctx["fire_timer"] = timer
        if timer > 1.4:
            ctx["fire_timer"] = 0.0
            ctx["projectile"] = {"damage": 10, "speed": 200}
            return "success"
        return "running"

class BossPhaseMachine:
    def __init__(self, phases: int = 5):
        self.phase = 0
        self.phases = phases
        self.health = float(phases * 35)
        self.max_health = self.health
        self.patterns = ["dash", "projectile_spread", "area_denial", "summon", "laser", "orbital", "beam"]
    def update(self, dt: float, player_pos: Tuple[float, float]) -> Dict[str, Any]:
        thresh = 1.0 - float(self.phase + 1) / float(self.phases)
        if self.health < self.max_health * thresh and self.phase < self.phases - 1:
            self.phase += 1
        pattern = self.patterns[self.phase % len(self.patterns)]
        return {"phase": self.phase, "pattern": pattern, "health": self.health}
    def take_damage(self, amt: float) -> bool:
        self.health = max(0.0, self.health - amt)
        return self.health <= 0.0

ATTACK_PATTERNS: Dict[str, Dict[str, Any]] = {
    "pat_0": {"windup": 0.25, "active": 0.45, "damage": 5, "range": 1.2, "optical": "dash"},
    "pat_1": {"windup": 0.29, "active": 0.53, "damage": 6, "range": 1.5, "optical": "projectile"},
}

def select_pattern(phase: int, entropy: float) -> Dict[str, Any]:
    key = f"pat_{(phase * 23 + int(entropy * 100)) % 2}"
    return ATTACK_PATTERNS.get(key, ATTACK_PATTERNS["pat_0"])
