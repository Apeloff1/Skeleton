"""Advanced procedural generator.
Multi-biome graphs, optical density, pack tiers, and era-scaled boss.
"""
from typing import Any, Dict, List

class ProceduralGenerator:
    BIOMES = ["ash_tunnel", "crystal_cavern", "void_rift", "ember_hall"]

    def generate(self, rooms: int, optical: float, era: str) -> Dict[str, Any]:
        graph = []
        for i in range(rooms):
            biome = self.BIOMES[i % len(self.BIOMES)]
            neighbors = [i - 1] if i > 0 else []
            if i < rooms - 1:
                neighbors.append(i + 1)
            density = optical * (1.0 + (i / max(1, rooms)))
            graph.append({"id": i, "neighbors": neighbors, "biome": biome, "density": round(density, 2)})
        packs = [{"room": i % rooms, "tier": "elite" if optical > 0.9 else "pack", "value": int(8 * (1 + optical * 0.5))} for i in range(rooms * 2)]
        boss = {"room": rooms - 1, "phase": 4 + int(optical * 2), "optical": optical, "era": era}
        return {
            "rooms": rooms,
            "graph": len(graph),
            "packs": len(packs),
            "boss": boss,
            "biomes": list(set(g["biome"] for g in graph)),
            "era": era,
            "optical": optical,
            "schema": "skeleton.proc.gen.v2",
        }
