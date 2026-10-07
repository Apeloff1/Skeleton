#!/usr/bin/env python3
"""
Reputation Decay + Leaderboards + Challenges System
Adds long-term progression mechanics:
- Reputation decay for inactivity
- Category and global leaderboards
- Mastery challenges and leaderboards
"""

from gameforge.roles.seat_assignment_system.advanced_voting_reputation_system import AdvancedVotingReputationSystem
from typing import Dict, List
from datetime import datetime, timedelta

class ReputationDecayLeaderboardSystem(AdvancedVotingReputationSystem):
    def __init__(self):
        super().__init__()
        self.last_activity: Dict[str, datetime] = {}  # agent_id -> last active time
        self.challenges: List[Dict] = []
    
    def record_activity(self, agent_id: str):
        """Record that an agent was active today."""
        self.last_activity[agent_id] = datetime.utcnow()
    
    def apply_reputation_decay(self):
        """Apply daily reputation decay to inactive agents."""
        now = datetime.utcnow()
        decayed_count = 0
        
        for agent_id, rep in self.agent_reputations.items():
            last_active = self.last_activity.get(agent_id, now - timedelta(days=40))
            days_inactive = (now - last_active).days
            
            if days_inactive >= 30:
                decay_amount = min(5, days_inactive - 29)  # 1 point per day after 30
                rep.overall_reputation = max(0, rep.overall_reputation - decay_amount)
                decayed_count += 1
        
        print(f"Applied reputation decay to {decayed_count} inactive agents.")
        return decayed_count
    
    def get_global_leaderboard(self, top_n: int = 20) -> List[Dict]:
        """Return top agents by overall reputation."""
        sorted_agents = sorted(
            self.agent_reputations.items(),
            key=lambda x: x[1].overall_reputation,
            reverse=True
        )
        
        return [
            {
                "rank": idx + 1,
                "agent_id": agent_id,
                "reputation": round(rep.overall_reputation, 1),
                "total_contributions": rep.total_contributions,
                "successful_handoffs": rep.successful_handoffs
            }
            for idx, (agent_id, rep) in enumerate(sorted_agents[:top_n])
        ]
    
    def get_category_leaderboard(self, category: str, top_n: int = 20) -> List[Dict]:
        """Return top agents in a specific category by mastery."""
        agents_in_category = [
            (agent_id, rep) for agent_id, rep in self.agent_reputations.items()
            if category in rep.category_mastery
        ]
        
        sorted_agents = sorted(
            agents_in_category,
            key=lambda x: x[1].category_mastery.get(category, 0),
            reverse=True
        )
        
        return [
            {
                "rank": idx + 1,
                "agent_id": agent_id,
                "mastery_score": round(rep.category_mastery.get(category, 0), 1),
                "mastery_level": self.get_agent_mastery_level(agent_id, category),
                "overall_reputation": round(rep.overall_reputation, 1)
            }
            for idx, (agent_id, rep) in enumerate(sorted_agents[:top_n])
        ]
    
    def create_mastery_challenge(self, category: str, target_mastery: float, 
                                  reward_reputation: float, description: str):
        """Create a new mastery challenge."""
        challenge = {
            "id": len(self.challenges) + 1,
            "category": category,
            "target_mastery": target_mastery,
            "reward_reputation": reward_reputation,
            "description": description,
            "created_at": datetime.utcnow().isoformat(),
            "completed_by": []
        }
        self.challenges.append(challenge)
        return challenge
    
    def check_challenge_completion(self, agent_id: str, category: str, current_mastery: float):
        """Check and award completed challenges."""
        for challenge in self.challenges:
            if challenge["category"] == category and current_mastery >= challenge["target_mastery"]:
                if agent_id not in challenge["completed_by"]:
                    challenge["completed_by"].append(agent_id)
                    rep = self.get_or_create_reputation(agent_id)
                    rep.overall_reputation = min(100, rep.overall_reputation + challenge["reward_reputation"])
                    print(f"Agent {agent_id} completed challenge: {challenge['description']}")

if __name__ == "__main__":
    print("Reputation Decay + Leaderboards + Challenges System initialized.")
    print("Long-term progression and healthy competition mechanics active.")