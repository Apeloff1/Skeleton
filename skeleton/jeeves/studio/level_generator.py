"""Level generation subsystem (4x).
Procedural tilemap, entity placement, hazard distribution, optical-class binding, room connectivity, seed digest.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import hashlib, json, math, random

class LevelGenerator:
    def __init__(self, seed: int = 8847291):
        self.rng = random.Random(seed)
        self.seed = seed

    def generate(self, width: int = 80, height: int = 60, patterns: Dict[str, Any] = None) -> Dict[str, Any]:
        patterns = patterns or {}
        tiles = [[0 for _ in range(width)] for _ in range(height)]
        entities = []
        for y in range(height):
            for x in range(width):
                n = self.rng.random()
                optical = patterns.get("optical_classes", {})
                wall_bias = optical.get("tile_wall", 0.2)
                hazard_bias = optical.get("tile_hazard", 0.1)
                if n < wall_bias:
                    tiles[y][x] = 1
                elif n < wall_bias + hazard_bias:
                    tiles[y][x] = 2
                else:
                    tiles[y][x] = 0
        for i in range(width // 8):
            x = self.rng.randint(2, width-3)
            for y in range(2, height-2):
                if self.rng.random() < 0.7:
                    tiles[y][x] = 0
        density = patterns.get("pack", {}).get("density", 0.35)
        pack_count = int(width * height * density * 0.04)
        for i in range(pack_count):
            x, y = self.rng.randint(3, width-4), self.rng.randint(3, height-4)
            entities.append({"type": "pack", "x": x, "y": y, "variant": self.rng.choice(["small","medium","large"]), "value": 8 + i%10})
        enemy_count = max(4, int(width * 0.1))
        for i in range(enemy_count):
            x, y = self.rng.randint(5, width-6), self.rng.randint(5, height-6)
            entities.append({"type": "enemy", "x": x, "y": y, "behavior": self.rng.choice(["patrol","chaser","turret"]), "health": 25 + i%15})
        entities.append({"type": "boss_spawn", "x": width//2, "y": height//2, "phases": patterns.get("state_machine_phases", 4)})
        digest = hashlib.sha256(json.dumps(tiles).encode()).hexdigest()[:16]
        return {
            "schema": "skeleton.level.v2",
            "seed": self.seed,
            "width": width,
            "height": height,
            "tiles": tiles,
            "entities": entities,
            "optical_classes": patterns.get("optical_classes", {}),
            "digest": digest,
            "pack_count": pack_count,
            "enemy_count": enemy_count,
        }

    def to_godot_tilemap(self, level: Dict[str, Any]) -> str:
        lines = ["# TileMap data v2"]
        for y, row in enumerate(level["tiles"]):
            for x, t in enumerate(row):
                if t:
                    lines.append(f"{x},{y},{t}")
        return "\\n".join(lines)
