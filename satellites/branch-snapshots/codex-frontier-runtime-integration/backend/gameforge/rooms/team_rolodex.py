from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class TeamMember:
    agent_id: str
    name: str
    current_role: Optional[str] = None
    specialties: List[str] = field(default_factory=list)
    contributions_count: int = 0
    last_active: str = "now"

class TeamRolodex:
    """
    Directory and index of all agents/team members currently in the room.
    Acts as the room's team rolodex with search and category indexing.
    """

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.members: Dict[str, TeamMember] = {}
        self.category_index: Dict[str, List[str]] = {}  # category -> list of agent_ids

    def add_member(self, member: TeamMember):
        self.members[member.agent_id] = member
        for spec in member.specialties:
            if spec not in self.category_index:
                self.category_index[spec] = []
            self.category_index[spec].append(member.agent_id)

    def get_member(self, agent_id: str) -> Optional[TeamMember]:
        return self.members.get(agent_id)

    def search_by_specialty(self, specialty: str) -> List[TeamMember]:
        agent_ids = self.category_index.get(specialty, [])
        return [self.members[aid] for aid in agent_ids if aid in self.members]

    def get_all_members(self) -> List[TeamMember]:
        return list(self.members.values())

    def update_contribution(self, agent_id: str):
        if agent_id in self.members:
            self.members[agent_id].contributions_count += 1

    def get_rolodex_summary(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "total_members": len(self.members),
            "categories": list(self.category_index.keys()),
            "top_contributors": sorted(
                self.members.values(),
                key=lambda m: m.contributions_count,
                reverse=True
            )[:5]
        }
