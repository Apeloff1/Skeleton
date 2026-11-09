#!/usr/bin/env python3
"""
Agent Seat Cycling Engine
Handles intelligent cycling of agents through 100 role seats in each room.
Includes quality gates, handoff protocols, and performance tracking.
Integrated with JeevesZaibatsu CNS.
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class AgentHandoff:
    from_seat: int
    to_seat: int
    agent_id: str
    timestamp: str
    quality_score: float
    notes: str

class AgentSeatCyclingEngine:
    def __init__(self, room_seat_manager):
        self.room = room_seat_manager
        self.handoff_history: List[AgentHandoff] = []
        self.cycle_count = 0
    
    def assign_next_available_seat(self, agent_id: str) -> Optional[int]:
        """Assign agent to the next available seat."""
        seat_id = self.room.get_next_available_seat()
        if seat_id is None:
            return None
        
        success = self.room.assign_agent_to_seat(seat_id, agent_id)
        if success:
            return seat_id
        return None
    
    def complete_seat_work(self, seat_id: int, quality_score: float, notes: str = "") -> bool:
        """Mark seat work as complete and record quality."""
        success = self.room.release_seat(seat_id, quality_score)
        if success:
            # Record handoff for future analysis
            handoff = AgentHandoff(
                from_seat=seat_id,
                to_seat=-1,  # Will be filled on next assignment
                agent_id=self.room.seats[seat_id].current_agent_id or "unknown",
                timestamp=datetime.utcnow().isoformat(),
                quality_score=quality_score,
                notes=notes
            )
            self.handoff_history.append(handoff)
        return success
    
    def cycle_all_seats(self):
        """Reset all completed/in_review seats back to available."""
        self.room.cycle_seats()
        self.cycle_count += 1
        print(f"Cycle {self.cycle_count} completed. All seats reset for next round.")
    
    def get_high_performing_seats(self, min_score: float = 85.0) -> List[int]:
        """Return seats that consistently produce high quality work."""
        return [
            seat_id for seat_id, seat in self.room.seats.items()
            if seat.quality_score >= min_score
        ]
    
    def get_low_performing_seats(self, max_score: float = 70.0) -> List[int]:
        """Return seats that may need review or role improvement."""
        return [
            seat_id for seat_id, seat in self.room.seats.items()
            if seat.quality_score > 0 and seat.quality_score <= max_score
        ]
    
    def generate_cycling_report(self) -> Dict:
        """Generate a report on cycling performance and seat health."""
        report = {
            "room_id": self.room.room_id,
            "category": self.room.category,
            "total_cycles": self.cycle_count,
            "total_handoffs": len(self.handoff_history),
            "average_quality": sum(h.quality_score for h in self.handoff_history) / len(self.handoff_history) if self.handoff_history else 0,
            "high_performing_seats": len(self.get_high_performing_seats()),
            "low_performing_seats": len(self.get_low_performing_seats()),
            "seat_status": self.room.get_seat_status_report()
        }
        return report

if __name__ == "__main__":
    print("Agent Seat Cycling Engine initialized.")
    print("Requires a RoomSeatManager instance to operate.")