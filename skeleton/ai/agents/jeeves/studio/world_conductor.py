"""World conductor (10x creative).
Biome generation, room graph, connectivity, optical-driven difficulty, boss arena placement.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import hashlib, json, random

BIOMES = ["ash_tunnel", "crystal_cavern", "rust_foundry", "void_rift", "ember_hall"]

class WorldConductor:
    def __init__(self, seed: int = 8847291):
        self.rng = random.Random(seed)
        self.seed = seed

    def build(self, patterns: Dict[str, Any] = None) -> Dict[str, Any]:
        patterns = patterns or {}
        optical = patterns.get("optical_classes", {})
        rooms = []
        for i in range(12):
            biome = self.rng.choice(BIOMES)
            difficulty = 0.3 + optical.get("tile_hazard", 0.1) * 2 + (i * 0.05)
            rooms.append({
                "id": i,
                "biome": biome,
                "difficulty": round(min(1.0, difficulty), 2),
                "packs": 2 + self.rng.randint(0, 3),
                "enemies": 1 + self.rng.randint(0, 2),
                "connections": [j for j in range(12) if abs(j - i) <= 2 and j != i][:3],
            })
        boss_room = {"id": 12, "biome": "void_rift", "difficulty": 0.95, "phases": patterns.get("state_machine_phases", 5)}
        digest = hashlib.sha256(json.dumps(rooms).encode()).hexdigest()[:16]
        return {
            "schema": "skeleton.world.v3",
            "seed": self.seed,
            "rooms": rooms,
            "boss_room": boss_room,
            "digest": digest,
            "optical_bias": optical,
        }

    def to_godot_nodes(self, world: Dict[str, Any]) -> str:
        lines = ["# World nodes"]
        for r in world["rooms"]:
            lines.append(f"Room_{r['id']} biome={r['biome']} diff={r['difficulty']}")
        return "\\n".join(lines)
