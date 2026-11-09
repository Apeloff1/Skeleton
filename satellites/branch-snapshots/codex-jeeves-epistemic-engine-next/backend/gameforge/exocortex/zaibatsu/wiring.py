from __future__ import annotations
"""
Mega Man style wiring + cross-wiring.

Systems are 'stages'. Beating (mastering) a subsystem unlocks a weapon/ability
that cross-wires into other subsystems — same idea as robot master weapons.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set


@dataclass
class WireNode:
    node_id: str
    domain: str  # math | neuro | pfc | twin | judgement | vox | security
    mastered: bool = False
    weapon: Optional[str] = None  # unlocked ability name
    links: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# Classic-style weapon unlock table
CROSS_WIRING = {
    "math": {"weapon": "AtomicFire_Calc", "boosts": ["judgement", "pfc"]},
    "neuro": {"weapon": "BubbleLead_Affect", "boosts": ["twin", "pfc"]},
    "pfc": {"weapon": "MetalBlade_Executive", "boosts": ["judgement", "vox"]},
    "twin": {"weapon": "TimeStopper_Memory", "boosts": ["neuro", "security"]},
    "judgement": {"weapon": "CrashBomber_Skeptic", "boosts": ["vox", "security"]},
    "vox": {"weapon": "ThunderBeam_Command", "boosts": ["pfc", "security"]},
    "security": {"weapon": "LeafShield_Defense", "boosts": ["twin", "math"]},
}


class MegaWiringGrid:
    def __init__(self):
        self.nodes: Dict[str, WireNode] = {
            k: WireNode(node_id=k, domain=k, links=list(v["boosts"]))
            for k, v in CROSS_WIRING.items()
        }
        self.unlocked_weapons: Set[str] = set()
        self.log: List[dict] = []

    def master(self, domain: str) -> Dict[str, Any]:
        node = self.nodes.get(domain)
        if not node:
            return {"ok": False, "error": "unknown_domain"}
        node.mastered = True
        w = CROSS_WIRING[domain]["weapon"]
        node.weapon = w
        self.unlocked_weapons.add(w)
        # cross-wire: mark links as reinforced
        reinforced = []
        for b in CROSS_WIRING[domain]["boosts"]:
            if b in self.nodes:
                if domain not in self.nodes[b].links:
                    self.nodes[b].links.append(domain)
                reinforced.append(b)
        self.log.append({"event": "master", "domain": domain, "weapon": w, "reinforced": reinforced})
        return {"ok": True, "weapon": w, "reinforced": reinforced, "weapons": sorted(self.unlocked_weapons)}

    def cross_bonus(self, domain: str) -> float:
        """Numeric bias for routing when cross-wired."""
        node = self.nodes.get(domain)
        if not node:
            return 0.0
        bonus = 0.15 if node.mastered else 0.0
        bonus += 0.05 * sum(1 for l in node.links if self.nodes.get(l) and self.nodes[l].mastered)
        return bonus

    def status(self) -> Dict[str, Any]:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "weapons": sorted(self.unlocked_weapons),
            "log_tail": self.log[-10:],
        }
