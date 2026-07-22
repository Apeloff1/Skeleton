#!/usr/bin/env python3
"""
Advanced Voting + Reputation + Mastery System
Extends the basic voting system with agent reputation, mastery levels per category,
and dynamic vote weighting based on proven competency.
"""

from gameforge.roles.seat_assignment_system.role_contribution_voting_system import RoleContributionVotingSystem, VoteType
from typing import Dict, List
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class AgentReputation:
    agent_id: str
    overall_reputation: float = 50.0  # 0-100
    category_mastery: Dict[str, float] = field(default_factory=dict)  # category -> mastery score
    total_contributions: int = 0
    successful_handoffs: int = 0
    failed_quality_gates: int = 0

class AdvancedVotingReputationSystem(RoleContributionVotingSystem):
    def __init__(self):
        super().__init__()
        self.agent_reputations: Dict[str, AgentReputation] = {}
        self.mastery_thresholds = {
            "novice": 30,
            "competent": 55,
            "expert": 75,
            "master": 90
        }
    
    def get_or_create_reputation(self, agent_id: str) -> AgentReputation:
        if agent_id not in self.agent_reputations:
            self.agent_reputations[agent_id] = AgentReputation(agent_id=agent_id)
        return self.agent_reputations[agent_id]
    
    def update_reputation_after_handoff(self, agent_id: str, category: str, 
                                        fidelity_score: float, passed: bool):
        """Update agent's reputation and mastery after a handoff attempt."""
        rep = self.get_or_create_reputation(agent_id)
        rep.total_contributions += 1
        
        if passed:
            rep.successful_handoffs += 1
            # Increase reputation
            rep.overall_reputation = min(100, rep.overall_reputation + 2)
            # Increase category mastery
            current_mastery = rep.category_mastery.get(category, 40.0)
            rep.category_mastery[category] = min(100, current_mastery + 3)
        else:
            rep.failed_quality_gates += 1
            # Decrease reputation slightly
            rep.overall_reputation = max(0, rep.overall_reputation - 1)
        
        # Recalculate overall reputation based on success rate
        if rep.total_contributions > 5:
            success_rate = rep.successful_handoffs / rep.total_contributions
            rep.overall_reputation = (success_rate * 80) + 20  # Base 20 + up to 80 from success rate
    
    def get_vote_weight(self, voter_agent_id: str, category: str) -> float:
        """Calculate dynamic vote weight based on reputation and mastery."""
        rep = self.get_or_create_reputation(voter_agent_id)
        
        base_weight = 1.0
        mastery = rep.category_mastery.get(category, 40.0)
        
        # Higher mastery = higher vote weight
        if mastery >= self.mastery_thresholds["master"]:
            return base_weight * 2.0
        elif mastery >= self.mastery_thresholds["expert"]:
            return base_weight * 1.5
        elif mastery >= self.mastery_thresholds["competent"]:
            return base_weight * 1.2
        else:
            return base_weight
    
    def cast_weighted_vote(self, seat_id: int, voter_agent_id: str, target_agent_id: str,
                           vote: VoteType, feedback: str, category: str):
        """Cast a vote with dynamically calculated weight based on voter mastery."""
        weight = self.get_vote_weight(voter_agent_id, category)
        self.cast_vote(seat_id, voter_agent_id, target_agent_id, vote, feedback, weight)
    
    def get_agent_mastery_level(self, agent_id: str, category: str) -> str:
        """Return current mastery level for an agent in a category."""
        rep = self.get_or_create_reputation(agent_id)
        mastery = rep.category_mastery.get(category, 40.0)
        
        if mastery >= self.mastery_thresholds["master"]:
            return "master"
        elif mastery >= self.mastery_thresholds["expert"]:
            return "expert"
        elif mastery >= self.mastery_thresholds["competent"]:
            return "competent"
        else:
            return "novice"
    
    def generate_reputation_report(self) -> Dict:
        """Generate system-wide reputation and mastery overview."""
        return {
            "total_agents_tracked": len(self.agent_reputations),
            "average_reputation": sum(r.overall_reputation for r in self.agent_reputations.values()) / len(self.agent_reputations) if self.agent_reputations else 0,
            "top_performers": sorted(
                [(aid, rep.overall_reputation) for aid, rep in self.agent_reputations.items()],
                key=lambda x: x[1], reverse=True
            )[:10]
        }

if __name__ == "__main__":
    print("Advanced Voting + Reputation + Mastery System initialized.")
    print("Dynamic vote weighting and long-term agent progression tracking active.")