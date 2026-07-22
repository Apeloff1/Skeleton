from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class Role:
    """
    A single specialized role that an agent can cycle through.
    Each role evaluates, adds to, refines, and quality-controls work.
    """
    role_id: str
    name: str
    category: str                    # e.g., "Design", "Technical", "Analytical", "Creative"
    specialty: str                   # Niche focus area
    perspective: str                 # How this role views the work
    traits: List[str]                # Key personality/trait keywords
    skills: List[str]                # Specific capabilities
    prompt_template: str             # Template used to instruct the agent in this role
    quality_criteria: List[str]      # What "high quality" looks like from this role
    weight: float = 1.0              # Influence weight in cycling

    def apply(self, work: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        This method would be called during role cycling.
        In practice, this would call an LLM with the prompt_template + current work.
        For now, it returns a structured refinement dict.
        """
        return {
            "role": self.name,
            "evaluation": f"Evaluated from {self.specialty} perspective.",
            "additions": [],
            "refinements": [],
            "quality_score": 0.85,   # Placeholder - real system would compute this
            "notes": f"Role {self.name} processed the work."
        }


@dataclass
class RoleSet:
    """A collection of 100 roles assigned to a room type or specific room."""
    room_category: str
    roles: List[Role] = field(default_factory=list)

    def get_role(self, role_id: str) -> Role | None:
        for role in self.roles:
            if role.role_id == role_id:
                return role
        return None

    def get_roles_by_category(self, category: str) -> List[Role]:
        return [r for r in self.roles if r.category == category]
