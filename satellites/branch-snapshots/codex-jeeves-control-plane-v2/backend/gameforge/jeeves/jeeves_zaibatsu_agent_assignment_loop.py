#!/usr/bin/env python3
"""
JeevesZaibatsu Live Agent Assignment Loop
Integrates the Agent-to-Seat Matching Engine into daily operations.
Automatically recommends and assigns agents to the best available seats based on skills, mastery, and reputation.
"""

from jeeves_zaibatsu_orchestrator import JeevesZaibatsuOrchestrator
from ..agents.agent_seat_matching_engine import AgentSeatMatchingEngine, AgentProfile

class JeevesZaibatsuAgentAssignmentLoop(JeevesZaibatsuOrchestrator):
    def __init__(self, manifest_path: str, skill_bank: dict, mastery_system: dict):
        super().__init__(manifest_path)
        self.matching_engine = AgentSeatMatchingEngine(skill_bank, mastery_system)
    
    def recommend_and_assign_best_seat(self, room_id: str, agent_profile: AgentProfile) -> dict:
        """Find the best available seat in a room for an agent and assign them."""
        if room_id not in self.rooms:
            return {"success": False, "reason": "Room not found"}
        
        record = self.rooms[room_id]
        
        # Get currently available seats
        available_seats = [
            {
                "seat_id": seat_id,
                "role": {
                    "role_id": seat.role_id,
                    "category": seat.category,
                    "skills": [],  # Would pull from role data in real system
                    "name": seat.role_id
                }
            }
            for seat_id, seat in record.seat_manager.seats.items()
            if seat.status == "available"
        ]
        
        if not available_seats:
            return {"success": False, "reason": "No available seats in room"}
        
        # Find best match
        best_match = self.matching_engine.recommend_seat_assignment(agent_profile, available_seats)
        
        if not best_match:
            return {"success": False, "reason": "No good match found"}
        
        # Assign the agent
        success = record.seat_manager.assign_agent_to_seat(best_match.seat_id, agent_profile.agent_id)
        
        if success:
            return {
                "success": True,
                "seat_id": best_match.seat_id,
                "role_id": best_match.role_id,
                "match_score": best_match.match_score,
                "reasons": best_match.reasons
            }
        else:
            return {"success": False, "reason": "Failed to assign seat"}
    
    def auto_assign_top_performers(self, category: str, top_agents: list):
        """Automatically assign top-performing agents to high-priority seats in a category."""
        if category not in self.category_index:
            return {"success": False, "reason": "Category has no rooms"}
        
        assignments = []
        for room_id in self.category_index[category][:3]:  # Limit to first 3 rooms for now
            for agent in top_agents:
                result = self.recommend_and_assign_best_seat(room_id, agent)
                if result.get("success"):
                    assignments.append(result)
        
        return {
            "success": True,
            "assignments_made": len(assignments),
            "details": assignments
        }

if __name__ == "__main__":
    print("JeevesZaibatsu Live Agent Assignment Loop initialized.")
    print("Ready for skill + mastery + reputation based auto-assignment.")