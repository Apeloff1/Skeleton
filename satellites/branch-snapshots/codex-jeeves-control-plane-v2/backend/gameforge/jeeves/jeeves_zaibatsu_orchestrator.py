#!/usr/bin/env python3
"""
JeevesZaibatsu Orchestrator
Central nervous system for the entire 1000-room Zaibatsu CNS.
Manages room creation, agent assignment to Role-Seats, cycling, quality enforcement,
and high-level coordination across all categories.
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..rooms.room_seat_manager import RoomSeatSystem
from ..rooms.agent_seat_cycling_engine import AgentSeatCyclingEngine

@dataclass
class RoomRecord:
    room_id: str
    category: str
    seat_manager: RoomSeatSystem
    cycling_engine: AgentSeatCyclingEngine
    created_at: str
    total_agents_assigned: int = 0
    average_quality: float = 0.0

class JeevesZaibatsuOrchestrator:
    def __init__(self, manifest_path: str):
        self.manifest_path = manifest_path
        self.rooms: Dict[str, RoomRecord] = {}
        self.category_index: Dict[str, List[str]] = {}  # category -> list of room_ids
        self.total_rooms = 0
        self.total_seats_managed = 0
        
    def create_room(self, room_id: str, category: str) -> RoomRecord:
        """Create a new room with 100 Role-Seats."""
        if room_id in self.rooms:
            return self.rooms[room_id]
        
        seat_manager = RoomSeatSystem(room_id=room_id, category=category)
        seat_manager.initialize_seats(self.manifest_path)
        
        cycling_engine = AgentSeatCyclingEngine(room_seat_manager=seat_manager)
        
        record = RoomRecord(
            room_id=room_id,
            category=category,
            seat_manager=seat_manager,
            cycling_engine=cycling_engine,
            created_at=datetime.utcnow().isoformat()
        )
        
        self.rooms[room_id] = record
        
        if category not in self.category_index:
            self.category_index[category] = []
        self.category_index[category].append(room_id)
        
        self.total_rooms += 1
        self.total_seats_managed += 100
        
        print(f"Created room {room_id} for category '{category}' with 100 seats.")
        return record
    
    def assign_agent_to_room(self, room_id: str, agent_id: str) -> Optional[int]:
        """Assign an agent to the next available seat in a room."""
        if room_id not in self.rooms:
            return None
        
        record = self.rooms[room_id]
        seat_id = record.cycling_engine.assign_next_available_seat(agent_id)
        
        if seat_id:
            record.total_agents_assigned += 1
            return seat_id
        return None
    
    def complete_agent_work(self, room_id: str, seat_id: int, quality_score: float, notes: str = ""):
        """Mark work complete on a seat and record quality."""
        if room_id not in self.rooms:
            return
        
        record = self.rooms[room_id]
        record.cycling_engine.complete_seat_work(seat_id, quality_score, notes)
        
        # Update room average quality
        self._update_room_average_quality(room_id)
    
    def _update_room_average_quality(self, room_id: str):
        """Recalculate average quality for the room."""
        record = self.rooms[room_id]
        scores = [s.quality_score for s in record.seat_manager.seats.values() if s.quality_score > 0]
        if scores:
            record.average_quality = sum(scores) / len(scores)
    
    def cycle_room(self, room_id: str):
        """Trigger a full cycle on a room (reset completed seats)."""
        if room_id in self.rooms:
            self.rooms[room_id].cycling_engine.cycle_all_seats()
    
    def get_system_status(self) -> Dict:
        """Get high-level status of the entire Zaibatsu."""
        return {
            "total_rooms": self.total_rooms,
            "total_seats_managed": self.total_seats_managed,
            "categories_active": len(self.category_index),
            "rooms_per_category": {cat: len(rooms) for cat, rooms in self.category_index.items()},
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_room_report(self, room_id: str) -> Optional[Dict]:
        """Get detailed report for a specific room."""
        if room_id not in self.rooms:
            return None
        record = self.rooms[room_id]
        return {
            "room_id": room_id,
            "category": record.category,
            "created_at": record.created_at,
            "total_agents_assigned": record.total_agents_assigned,
            "average_quality": round(record.average_quality, 2),
            "seat_status": record.seat_manager.get_seat_status_report(),
            "cycling_report": record.cycling_engine.generate_cycling_report()
        }

if __name__ == "__main__":
    print("JeevesZaibatsu Orchestrator initialized.")
    print("Ready to manage 1000+ rooms with 100 Role-Seats each.")