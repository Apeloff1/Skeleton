#!/usr/bin/env python3
"""
Blackboard Architecture for Zaibatsu CNS
A shared knowledge space where agents post hypotheses, partial results, and insights.
Classic Blackboard pattern for collaborative problem solving.
"""

import json
from typing import Dict, List
from datetime import datetime

class Blackboard:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.entries = []
        self.hypotheses = {}
        self.control = {}  # Who controls focus

    def post(self, agent_id: str, content: Dict, entry_type: str = "hypothesis"):
        """Any agent can post to the blackboard."""
        entry = {
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "content": content,
            "room_id": self.room_id
        }
        self.entries.append(entry)
        
        if entry_type == "hypothesis":
            self.hypotheses[agent_id] = entry
        
        return entry

    def read_blackboard(self, agent_id: str = None) -> List[Dict]:
        """Read current state of the blackboard."""
        if agent_id:
            return [e for e in self.entries if e["agent_id"] != agent_id]
        return self.entries

    def get_best_hypothesis(self) -> Dict:
        """Simple selection - in real version would use Judge + coherence scoring."""
        if not self.hypotheses:
            return None
        return list(self.hypotheses.values())[0]

if __name__ == "__main__":
    bb = Blackboard("room_test_001")
    print("Blackboard Architecture ready for collaborative agent work.")
