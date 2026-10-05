#!/usr/bin/env python3
"""
Trust & Reputation Engine
Implements faction/reputation style mechanics for agents and nodes.
Used for delegation, access control, and team formation.
"""

from typing import Dict
from datetime import datetime

class TrustReputationEngine:
    def __init__(self):
        self.agent_trust = {}   # agent_id -> trust_score
        self.node_trust = {}    # node_id -> trust_score

    def update_trust(self, entity_id: str, change: float, reason: str, entity_type: str = "agent"):
        """Update trust score for an agent or node."""
        if entity_type == "agent":
            current = self.agent_trust.get(entity_id, 50)
            new_score = max(0, min(100, current + change))
            self.agent_trust[entity_id] = new_score
        else:
            current = self.node_trust.get(entity_id, 50)
            new_score = max(0, min(100, current + change))
            self.node_trust[entity_id] = new_score

        return {
            "entity": entity_id,
            "new_trust": new_score,
            "change": change,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }

    def get_trust(self, entity_id: str, entity_type: str = "agent") -> float:
        if entity_type == "agent":
            return self.agent_trust.get(entity_id, 50)
        return self.node_trust.get(entity_id, 50)

    def can_delegate_to(self, agent_id: str, task_sensitivity: str = "normal") -> bool:
        """Check if an agent has sufficient trust for a task."""
        trust = self.get_trust(agent_id)
        thresholds = {"low": 30, "normal": 50, "high": 75, "critical": 90}
        return trust >= thresholds.get(task_sensitivity, 50)

if __name__ == "__main__":
    engine = TrustReputationEngine()
    print("Trust & Reputation Engine ready. Faction-style mechanics active.")
