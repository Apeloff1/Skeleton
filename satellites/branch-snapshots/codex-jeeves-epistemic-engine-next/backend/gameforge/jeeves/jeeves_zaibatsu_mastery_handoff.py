#!/usr/bin/env python3
"""
JeevesZaibatsu Mastery-Aware Handoff System
Integrates mastery level, reputation, and skill matching into the handoff decision process.
Only high-competency agents (based on mastery + reputation) can perform certain critical handoffs.
"""

from jeeves_zaibatsu_handoff_enforcer import JeevesZaibatsuHandoffEnforcer

class JeevesZaibatsuMasteryHandoff(JeevesZaibatsuHandoffEnforcer):
    def __init__(self, manifest_path: str):
        super().__init__(manifest_path)
        self.mastery_requirements = {
            "critical_seats": ["expert", "master"],  # Only experts/masters can handle critical seats
            "standard_seats": ["competent", "expert", "master"]
        }
    
    def can_agent_handoff(self, agent_id: str, seat_id: int, category: str, 
                          mastery_level: str, reputation: float) -> bool:
        """Check if an agent has sufficient mastery and reputation to perform a handoff on this seat."""
        
        # Critical seats require higher mastery
        if seat_id % 10 == 0:  # Example: every 10th seat is "critical"
            required_levels = self.mastery_requirements["critical_seats"]
            if mastery_level not in required_levels:
                return False
        
        # Minimum reputation threshold
        if reputation < 55:
            return False
        
        return True
    
    def perform_mastery_aware_handoff(self, room_id: str, seat_id: int, agent_id: str,
                                      mastery_level: str, reputation: float,
                                      quality_score: float, contributions: list, votes: list):
        """Perform handoff only if agent meets mastery and reputation requirements."""
        
        if not self.can_agent_handoff(agent_id, seat_id, self.rooms[room_id].category, 
                                      mastery_level, reputation):
            print(f"Handoff blocked: Agent {agent_id} does not meet mastery/reputation requirements for seat {seat_id}.")
            return False
        
        # Proceed with normal quality enforcement
        return self.complete_work_with_enforcement(
            room_id=room_id,
            seat_id=seat_id,
            quality_score=quality_score,
            contributions=contributions,
            votes=votes,
            notes=f"Mastery: {mastery_level} | Reputation: {reputation}"
        )

if __name__ == "__main__":
    print("JeevesZaibatsu Mastery-Aware Handoff System initialized.")
    print("Agents must meet mastery and reputation thresholds for critical handoffs.")