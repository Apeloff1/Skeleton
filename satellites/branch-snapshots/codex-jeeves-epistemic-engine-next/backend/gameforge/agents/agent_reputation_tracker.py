#!/usr/bin/env python3
"""
Agent Reputation Tracker
Lightweight tracker for monitoring agent reputation changes over time.
Can be used alongside the main reputation system for quick queries and updates.
"""

from typing import Dict
from datetime import datetime

class AgentReputationTracker:
    def __init__(self):
        self.reputation_log: Dict[str, list] = {}  # agent_id -> list of (timestamp, reputation, reason)
    
    def log_reputation_change(self, agent_id: str, new_reputation: float, reason: str):
        """Log a reputation change for an agent."""
        if agent_id not in self.reputation_log:
            self.reputation_log[agent_id] = []
        
        self.reputation_log[agent_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "reputation": new_reputation,
            "reason": reason
        })
    
    def get_reputation_history(self, agent_id: str, limit: int = 10) -> list:
        """Get recent reputation history for an agent."""
        if agent_id not in self.reputation_log:
            return []
        return self.reputation_log[agent_id][-limit:]
    
    def get_reputation_trend(self, agent_id: str) -> str:
        """Simple trend analysis for an agent's reputation."""
        history = self.get_reputation_history(agent_id, limit=5)
        if len(history) < 2:
            return "insufficient_data"
        
        recent = history[-1]["reputation"]
        previous = history[-2]["reputation"]
        
        if recent > previous + 2:
            return "improving"
        elif recent < previous - 2:
            return "declining"
        else:
            return "stable"

if __name__ == "__main__":
    print("Agent Reputation Tracker initialized.")
    print("Lightweight logging and trend analysis for agent reputation.")