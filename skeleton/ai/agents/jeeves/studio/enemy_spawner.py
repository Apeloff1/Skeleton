"""Enemy spawner. Spawns packs from optical and difficulty."""
from typing import Any, Dict, List
import random
class EnemySpawner:
    def spawn(self, optical: float, difficulty: float, room: int) -> List[Dict[str, Any]]:
        count = max(1, int(2 + difficulty * 2 - optical))
        return [{"type": "chaser" if optical > 0.9 else "patrol", "room": room, "health": int(20 * difficulty)} for _ in range(count)]
