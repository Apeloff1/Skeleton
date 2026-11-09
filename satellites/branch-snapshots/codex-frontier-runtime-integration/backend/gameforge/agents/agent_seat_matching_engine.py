#!/usr/bin/env python3
"""
Agent-to-Seat Matching Engine
Matches agents to the best available Role-Seats based on:
- Skill overlap with role requirements
- Current mastery level in the category
- Reputation score
- Historical performance in similar roles

Part of the JeevesZaibatsu CNS.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class AgentProfile:
    agent_id: str
    skills: List[str]
    category_mastery: Dict[str, float]  # category -> mastery score
    overall_reputation: float
    recent_performance: Dict[str, float]  # category -> avg fidelity

@dataclass
class SeatMatch:
    seat_id: int
    role_id: str
    category: str
    match_score: float
    reasons: List[str]

class AgentSeatMatchingEngine:
    def __init__(self, skill_bank: Dict, mastery_system: Dict):
        self.skill_bank = skill_bank
        self.mastery_system = mastery_system
    
    def calculate_match_score(self, agent: AgentProfile, role: Dict) -> SeatMatch:
        """Calculate how well an agent matches a specific role/seat."""
        score = 0.0
        reasons = []
        
        # Skill overlap (40% weight)
        role_skills = set(role.get("skills", []))
        agent_skills = set(agent.skills)
        overlap = len(role_skills & agent_skills)
        skill_score = (overlap / max(len(role_skills), 1)) * 40
        score += skill_score
        
        if overlap >= 3:
            reasons.append(f"Strong skill overlap ({overlap} shared skills)")
        elif overlap >= 1:
            reasons.append(f"Partial skill overlap ({overlap} shared skills)")
        else:
            reasons.append("No direct skill overlap - learning opportunity")
        
        # Mastery in category (35% weight)
        category = role.get("category", "unknown")
        mastery = agent.category_mastery.get(category, 30.0)
        mastery_score = (mastery / 100) * 35
        score += mastery_score
        
        if mastery >= 70:
            reasons.append(f"High mastery in {category} ({mastery:.0f})")
        elif mastery >= 50:
            reasons.append(f"Solid mastery in {category} ({mastery:.0f})")
        else:
            reasons.append(f"Developing mastery in {category} ({mastery:.0f})")
        
        # Reputation (25% weight)
        rep_score = (agent.overall_reputation / 100) * 25
        score += rep_score
        
        if agent.overall_reputation >= 80:
            reasons.append(f"High overall reputation ({agent.overall_reputation:.0f})")
        elif agent.overall_reputation >= 60:
            reasons.append(f"Good reputation ({agent.overall_reputation:.0f})")
        
        return SeatMatch(
            seat_id=-1,  # To be filled by caller
            role_id=role.get("role_id", "unknown"),
            category=category,
            match_score=round(score, 1),
            reasons=reasons
        )
    
    def find_best_seats_for_agent(self, agent: AgentProfile, available_seats: List[Dict], 
                                   top_n: int = 5) -> List[SeatMatch]:
        """Return the top N best matching seats for an agent."""
        matches = []
        
        for seat in available_seats:
            role = seat.get("role", {})
            match = self.calculate_match_score(agent, role)
            match.seat_id = seat.get("seat_id", -1)
            matches.append(match)
        
        # Sort by match score descending
        matches.sort(key=lambda x: x.match_score, reverse=True)
        return matches[:top_n]
    
    def recommend_seat_assignment(self, agent: AgentProfile, available_seats: List[Dict]) -> Optional[SeatMatch]:
        """Recommend the single best seat for an agent."""
        best_matches = self.find_best_seats_for_agent(agent, available_seats, top_n=1)
        return best_matches[0] if best_matches else None

if __name__ == "__main__":
    print("Agent-to-Seat Matching Engine initialized.")
    print("Uses skill overlap, mastery, and reputation for intelligent assignment.")