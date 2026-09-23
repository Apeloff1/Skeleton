#!/usr/bin/env python3
"""
JeevesZaibatsu Handoff Enforcer
Extends the orchestrator with strict quality enforcement on every agent handoff.
Integrates Contribution + Voting System, fidelity scoring, and automatic cycling.
"""

from jeeves_zaibatsu_orchestrator import JeevesZaibatsuOrchestrator
from ..roles.seat_assignment_system.role_contribution_voting_system import RoleContributionVotingSystem

class JeevesZaibatsuHandoffEnforcer(JeevesZaibatsuOrchestrator):
    def __init__(self, manifest_path: str):
        super().__init__(manifest_path)
        self.voting_system = RoleContributionVotingSystem()
        self.minimum_fidelity_for_handoff = 75.0
    
    def complete_work_with_enforcement(self, room_id: str, seat_id: int, 
                                       quality_score: float, contributions: list, 
                                       votes: list, notes: str = ""):
        """
        Complete work on a seat with full quality enforcement.
        Records contributions, applies votes, calculates fidelity, and only allows handoff if quality passes.
        """
        if room_id not in self.rooms:
            return False
        
        record = self.rooms[room_id]
        
        # Record all contributions
        for contrib in contributions:
            self.voting_system.record_contribution(
                seat_id=seat_id,
                agent_id=contrib["agent_id"],
                contribution_type=contrib["type"],
                content_summary=contrib["summary"],
                self_score=contrib.get("self_score", 0.0)
            )
        
        # Record all votes
        for vote in votes:
            self.voting_system.cast_vote(
                seat_id=seat_id,
                voter_agent_id=vote["voter_id"],
                target_agent_id=vote["target_id"],
                vote=vote["vote_type"],
                feedback=vote["feedback"],
                weight=vote.get("weight", 1.0)
            )
        
        # Evaluate
        evaluation = self.voting_system.evaluate_seat(seat_id)
        fidelity = evaluation["fidelity_score"]
        
        if fidelity >= self.minimum_fidelity_for_handoff:
            # Quality passed — allow handoff
            record.cycling_engine.complete_seat_work(seat_id, fidelity, notes)
            self._update_room_average_quality(room_id)
            return True
        else:
            # Quality failed — keep seat in review
            record.seat_manager.seats[seat_id].status = "in_review"
            print(f"Handoff blocked on seat {seat_id}. Fidelity {fidelity} below threshold {self.minimum_fidelity_for_handoff}.")
            return False
    
    def force_cycle_low_quality_seats(self, room_id: str, max_score: float = 60.0):
        """Force cycle seats that are stuck with low quality."""
        if room_id not in self.rooms:
            return
        
        record = self.rooms[room_id]
        low_seats = record.cycling_engine.get_low_performing_seats(max_score)
        
        for seat_id in low_seats:
            record.seat_manager.seats[seat_id].status = "available"
            record.seat_manager.seats[seat_id].quality_score = 0.0
        
        print(f"Forced cycle on {len(low_seats)} low-quality seats in room {room_id}.")

if __name__ == "__main__":
    print("JeevesZaibatsu Handoff Enforcer initialized with strict quality gates.")