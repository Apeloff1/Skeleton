"""Physics combat.
Impulse, knockback, and optical damage scaling.
"""
from typing import Any, Dict

class PhysicsCombat:
    def hit(self, attacker: str, target: str, base_dmg: float, optical: float, mass: float) -> Dict[str, Any]:
        dmg = base_dmg * (1.0 + optical * 0.3)
        knock = dmg / max(1.0, mass)
        return {
            "attacker": attacker,
            "target": target,
            "damage": round(dmg, 1),
            "knockback": round(knock, 2),
            "optical": optical,
            "schema": "skeleton.physics.combat.v1",
        }
