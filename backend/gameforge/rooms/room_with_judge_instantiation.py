#!/usr/bin/env python3
"""
Room Instantiation with Jeeves Judge Agent
Extended Room Instantiation Engine that automatically adds one Jeeves Judge per room.
"""

import json
from typing import Dict, List
from datetime import datetime

class RoomWithJudgeInstantiation:
    def __init__(self, judge_spawner_path: str):
        self.judge_spawner = self._load_json(judge_spawner_path)

    def _load_json(self, path: str) -> Dict:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return {}

    def instantiate_room_with_judge(self, room_id: str, category: str) -> Dict:
        """Create a room + automatically spawn its Jeeves Judge Agent."""
        room = {
            "room_id": room_id,
            "category": category,
            "instantiated_at": datetime.now().isoformat(),
            "status": "active",
            "has_judge": True,
            "judge_agent": {
                "agent_id": f"judge_{room_id}",
                "role": "judge_agent_jeeves",
                "type": "special_judge",
                "exocortex_linked": True,
                "voting_mode": "tiebreaker_only"
            },
            "seats": self._create_seats_with_judge(room_id),
            "bookshelf": {"type": "14_database_bookshelf", "status": "initialized"},
            "coherence": "validated"
        }
        return room

    def _create_seats_with_judge(self, room_id: str) -> List[Dict]:
        seats = [{"seat_id": f"{room_id}_seat_{i}", "type": "standard"} for i in range(8)]
        seats.append({
            "seat_id": f"{room_id}_judge_seat",
            "type": "special_judge",
            "reserved_for": "Jeeves (Exocortex-linked)"
        })
        return seats

if __name__ == "__main__":
    engine = RoomWithJudgeInstantiation(
        "/home/workdir/artifacts/gameforge_v1/gameforge/agents/judge_agent_spawning.py"
    )
    print("Room Instantiation with Jeeves Judge ready. Every room now has its Judge.")
