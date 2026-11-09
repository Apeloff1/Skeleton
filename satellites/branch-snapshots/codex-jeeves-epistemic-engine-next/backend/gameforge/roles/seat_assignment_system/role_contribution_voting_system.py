#!/usr/bin/env python3
"""
Role Contribution + Voting System
Implements mandatory quality control on top of Role-Seats.
Every agent must contribute, peer review, and vote on work before handoff.
Includes contribution mapping, ballot system, and fidelity scoring.
"""

import json
from typing import Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class VoteType(Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"

@dataclass
class Contribution:
    agent_id: str
    seat_id: int
    contribution_type: str  # e.g., "analysis", "design", "code", "review"
    content_summary: str
    timestamp: str
    quality_self_score: float

@dataclass
class Vote:
    voter_agent_id: str
    target_agent_id: str
    seat_id: int
    vote: VoteType
    feedback: str
    timestamp: str
    weight: float = 1.0  # Can be adjusted based on voter competency

@dataclass
class SeatContributionRecord:
    seat_id: int
    contributions: List[Contribution] = field(default_factory=list)
    votes: List[Vote] = field(default_factory=list)
    final_fidelity_score: float = 0.0
    status: str = "open"  # open, under_review, approved, changes_requested, rejected

class RoleContributionVotingSystem:
    def __init__(self):
        self.seat_records: Dict[int, SeatContributionRecord] = {}
        self.minimum_votes_required = 3
        self.approval_threshold = 0.75  # 75% positive votes needed
    
    def open_seat_for_contribution(self, seat_id: int):
        """Open a seat for contributions and voting."""
        if seat_id not in self.seat_records:
            self.seat_records[seat_id] = SeatContributionRecord(seat_id=seat_id)
    
    def record_contribution(self, seat_id: int, agent_id: str, contribution_type: str, 
                           content_summary: str, self_score: float):
        """Record an agent's contribution to a seat."""
        if seat_id not in self.seat_records:
            self.open_seat_for_contribution(seat_id)
        
        record = self.seat_records[seat_id]
        contrib = Contribution(
            agent_id=agent_id,
            seat_id=seat_id,
            contribution_type=contribution_type,
            content_summary=content_summary,
            timestamp=datetime.utcnow().isoformat(),
            quality_self_score=self_score
        )
        record.contributions.append(contrib)
    
    def cast_vote(self, seat_id: int, voter_agent_id: str, target_agent_id: str,
                  vote: VoteType, feedback: str, weight: float = 1.0):
        """Cast a peer review vote on another agent's work."""
        if seat_id not in self.seat_records:
            self.open_seat_for_contribution(seat_id)
        
        record = self.seat_records[seat_id]
        vote_obj = Vote(
            voter_agent_id=voter_agent_id,
            target_agent_id=target_agent_id,
            seat_id=seat_id,
            vote=vote,
            feedback=feedback,
            timestamp=datetime.utcnow().isoformat(),
            weight=weight
        )
        record.votes.append(vote_obj)
    
    def calculate_fidelity_score(self, seat_id: int) -> float:
        """Calculate final fidelity score based on votes and contributions."""
        if seat_id not in self.seat_records:
            return 0.0
        
        record = self.seat_records[seat_id]
        if not record.votes:
            return 0.0
        
        total_weight = 0.0
        positive_weight = 0.0
        
        for vote in record.votes:
            total_weight += vote.weight
            if vote.vote == VoteType.APPROVE:
                positive_weight += vote.weight
        
        if total_weight == 0:
            return 0.0
        
        score = (positive_weight / total_weight) * 100
        record.final_fidelity_score = round(score, 1)
        return record.final_fidelity_score
    
    def evaluate_seat(self, seat_id: int) -> Dict[str, Any]:
        """Evaluate whether a seat passes quality gates."""
        if seat_id not in self.seat_records:
            return {"status": "not_found"}
        
        record = self.seat_records[seat_id]
        score = self.calculate_fidelity_score(seat_id)
        
        approve_votes = sum(1 for v in record.votes if v.vote == VoteType.APPROVE)
        total_votes = len(record.votes)
        
        passed = (
            total_votes >= self.minimum_votes_required and
            score >= (self.approval_threshold * 100)
        )
        
        if passed:
            record.status = "approved"
        elif total_votes >= self.minimum_votes_required:
            record.status = "changes_requested" if score >= 50 else "rejected"
        else:
            record.status = "under_review"
        
        return {
            "seat_id": seat_id,
            "status": record.status,
            "fidelity_score": score,
            "total_votes": total_votes,
            "approve_votes": approve_votes,
            "passed": passed,
            "contributions_count": len(record.contributions)
        }
    
    def get_seat_audit_trail(self, seat_id: int) -> Dict:
        """Return full audit trail for a seat."""
        if seat_id not in self.seat_records:
            return {}
        
        record = self.seat_records[seat_id]
        return {
            "seat_id": seat_id,
            "status": record.status,
            "final_fidelity_score": record.final_fidelity_score,
            "contributions": [
                {
                    "agent_id": c.agent_id,
                    "type": c.contribution_type,
                    "summary": c.content_summary,
                    "self_score": c.quality_self_score,
                    "timestamp": c.timestamp
                } for c in record.contributions
            ],
            "votes": [
                {
                    "voter": v.voter_agent_id,
                    "target": v.target_agent_id,
                    "vote": v.vote.value,
                    "feedback": v.feedback,
                    "weight": v.weight,
                    "timestamp": v.timestamp
                } for v in record.votes
            ]
        }

if __name__ == "__main__":
    print("Role Contribution + Voting System initialized.")
    print("Mandatory peer review and quality gates active on all seats.")