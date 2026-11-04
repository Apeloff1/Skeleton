"""Launch-ready asset and content pipeline.

Generates structured game assets (rooms, items, dialogue, encounters)
that are immediately usable by the conductor and builders.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import random


class AssetPipeline:
    """Produces consistent, seedable game assets."""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        random.seed(seed)

    def generate_rooms(self, count: int = 10) -> List[Dict[str, Any]]:
        kinds = ["combat", "explore", "shop", "puzzle", "boss", "safe"]
        rooms = []
        for i in range(max(3, count)):
            kind = "boss" if i == count - 1 else random.choice(kinds[:-1])
            rooms.append({
                "id": f"room_{i:03d}",
                "kind": kind,
                "difficulty": round(i / max(count - 1, 1), 3),
                "width": random.randint(8, 18),
                "height": random.randint(6, 12),
                "exits": [],
                "loot_chance": 0.3 if kind == "combat" else 0.1,
            })
        for i, r in enumerate(rooms):
            if i > 0:
                r["exits"].append(rooms[i - 1]["id"])
            if i < len(rooms) - 1:
                r["exits"].append(rooms[i + 1]["id"])
        return rooms

    def generate_items(self, count: int = 12) -> List[Dict[str, Any]]:
        rarities = ["common", "common", "uncommon", "rare", "epic"]
        effects = ["none", "heal", "buff_damage", "buff_speed", "shield"]
        items = []
        for i in range(count):
            items.append({
                "id": f"item_{i:03d}",
                "name": f"Artifact_{i}",
                "rarity": rarities[min(i // 3, len(rarities) - 1)],
                "value": 5 + i * 4,
                "effect": random.choice(effects),
                "stackable": i % 3 != 0,
            })
        return items

    def generate_encounters(self, room_count: int = 10) -> List[Dict[str, Any]]:
        encounters = []
        for i in range(room_count):
            if i % 3 == 0:
                encounters.append({
                    "room": f"room_{i:03d}",
                    "enemies": [{"tier": 1 + i // 4, "count": 1 + i % 3}],
                    "boss": i == room_count - 1,
                })
        return encounters

    def generate_dialogue(self, title: str, nodes: int = 6) -> Dict[str, Any]:
        tree = []
        for i in range(nodes):
            tree.append({
                "id": f"dlg_{i:02d}",
                "speaker": "narrator" if i % 2 == 0 else "npc",
                "text": f"[{title}] The path continues at beat {i + 1}.",
                "next": f"dlg_{i+1:02d}" if i < nodes - 1 else None,
            })
        return {"title": title, "nodes": tree, "start": tree[0]["id"] if tree else None}

    def full_pack(self, title: str, room_count: int = 10) -> Dict[str, Any]:
        rooms = self.generate_rooms(room_count)
        items = self.generate_items()
        encounters = self.generate_encounters(room_count)
        dialogue = self.generate_dialogue(title)
        return {
            "title": title,
            "rooms": rooms,
            "items": items,
            "encounters": encounters,
            "dialogue": dialogue,
            "seed": self.seed,
            "ok": True,
        }
