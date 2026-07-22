#!/usr/bin/env python3
"""
Judge Agent Spawning System
Adds exactly one Jeeves Judge Agent to every room.
The Judge only votes on ties and has direct Exocortex access.
"""

import json
from typing import Dict, List
from datetime import datetime

class JudgeAgentSpawning:
    def __init__(self, judge_definition_path: str, exocortex_link: bool = True):
        self.judge_definition = self._load_json(judge_definition_path)
        self.exocortex_link = exocortex_link
        self.judges = {}

    def _load_json(self, path: str) -> Dict:
        with open(path, "r") as f:
            return json.load(f)

    def spawn_judge_for_room(self, room_id: str, category: str) -> Dict:
        """Spawn the Jeeves Judge Agent for a specific room."""
        judge = {
            "agent_id": f"judge_{room_id}",
            "room_id": room_id,
            "role_id": "judge_agent_jeeves",
            "type": "special_judge",
            "name": "Jeeves",
            "spawned_at": datetime.now().isoformat(),
            "status": "active",
            "exocortex_linked": self.exocortex_link,
            "voting_mode": "tiebreaker_only",
            "prompt_template": self.judge_definition["prompt_template"],
            "quality_criteria": self.judge_definition["quality_criteria"],
            "exocortex_access": self.judge_definition["exocortex_link"]["access"],
            "performance_metrics": {
                "ties_broken": 0,
                "coherence_maintained": 1.0,
                "exocortex_context_used": 0
            }
        }
        
        self.judges[room_id] = judge
        return judge

    def spawn_judges_for_all_rooms(self, rooms: List[Dict]) -> List[Dict]:
        """Add a Judge Agent to every room."""
        spawned_judges = []
        for room in rooms:
            judge = self.spawn_judge_for_room(room["room_id"], room["category"])
            spawned_judges.append(judge)
        return spawned_judges

    def get_judge_for_room(self, room_id: str) -> Dict:
        return self.judges.get(room_id)

if __name__ == "__main__":
    spawner = JudgeAgentSpawning(
        "/home/workdir/artifacts/gameforge_v1/gameforge/agents/judge_agent_definition.json"
    )
    print("Judge Agent Spawning System ready. One Jeeves per room.")
