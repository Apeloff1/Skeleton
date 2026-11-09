#!/usr/bin/env python3
"""
Room Seat Manager
Manages 100 specialized role seats inside each room.
Handles agent assignment to seats, cycling, handoff, and quality enforcement.
Part of the Zaibatsu CNS Role-Seat QC System.
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SeatState:
    seat_id: int
    role_id: str
    category: str
    current_agent_id: Optional[str] = None
    last_assigned: Optional[str] = None
    quality_score: float = 0.0
    handoff_count: int = 0
    status: str = "available"  # available, occupied, in_review, completed

@dataclass
class RoomSeatSystem:
    room_id: str
    category: str
    seats: Dict[int, SeatState] = field(default_factory=dict)
    seat_manifest: Dict = field(default_factory=dict)
    
    def initialize_seats(self, manifest_path: str):
        """Load 100 seats from the role seat manifest."""
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        category_seats = manifest["seat_assignments"].get(self.category, [])
        
        for seat_data in category_seats:
            seat_id = seat_data["seat_id"]
            self.seats[seat_id] = SeatState(
                seat_id=seat_id,
                role_id=seat_data["role_id"],
                category=self.category,
                status="available"
            )
        
        self.seat_manifest = manifest
        print(f"Room {self.room_id} initialized with {len(self.seats)} seats for category '{self.category}'")
    
    def assign_agent_to_seat(self, seat_id: int, agent_id: str) -> bool:
        """Assign an agent to a specific seat."""
        if seat_id not in self.seats:
            return False
        
        seat = self.seats[seat_id]
        if seat.status != "available":
            return False
        
        seat.current_agent_id = agent_id
        seat.last_assigned = datetime.utcnow().isoformat()
        seat.status = "occupied"
        seat.handoff_count += 1
        return True
    
    def release_seat(self, seat_id: int, quality_score: float = 0.0):
        """Release a seat after work is complete and record quality."""
        if seat_id not in self.seats:
            return False
        
        seat = self.seats[seat_id]
        seat.quality_score = quality_score
        seat.current_agent_id = None
        seat.status = "completed" if quality_score >= 80 else "in_review"
        return True
    
    def get_next_available_seat(self) -> Optional[int]:
        """Find the next available seat for assignment."""
        for seat_id, seat in self.seats.items():
            if seat.status == "available":
                return seat_id
        return None
    
    def cycle_seats(self):
        """Reset completed seats back to available for next cycle."""
        for seat in self.seats.values():
            if seat.status in ["completed", "in_review"]:
                seat.status = "available"
                seat.quality_score = 0.0
    
    def get_seat_status_report(self) -> Dict:
        """Generate current status report for all seats."""
        report = {
            "room_id": self.room_id,
            "category": self.category,
            "total_seats": len(self.seats),
            "available": sum(1 for s in self.seats.values() if s.status == "available"),
            "occupied": sum(1 for s in self.seats.values() if s.status == "occupied"),
            "completed": sum(1 for s in self.seats.values() if s.status == "completed"),
            "in_review": sum(1 for s in self.seats.values() if s.status == "in_review"),
            "average_quality": sum(s.quality_score for s in self.seats.values()) / len(self.seats) if self.seats else 0
        }
        return report

if __name__ == "__main__":
    print("Room Seat Manager initialized.")
    print("Use initialize_seats() with the role_seat_manifest.json to activate 100 seats per room.")