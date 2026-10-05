from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List
from gameforge.roles.base_role import Role, RoleSet

class RoleManager:
    """
    Manages all role sets for the 1000 rooms.
    Each room category has its own specialized set of 100 roles.
    """

    def __init__(self, role_sets_dir: str = "gameforge/roles/role_sets"):
        self.role_sets_dir = Path(role_sets_dir)
        self.role_sets: Dict[str, RoleSet] = {}
        self._load_all_role_sets()

    def _load_all_role_sets(self):
        """Load role sets from JSON files in role_sets directory."""
        if not self.role_sets_dir.exists():
            self.role_sets_dir.mkdir(parents=True, exist_ok=True)
            return

        for file in self.role_sets_dir.glob("*.json"):
            category = file.stem
            with open(file, "r") as f:
                data = json.load(f)
            roles = [Role(**r) for r in data.get("roles", [])]
            self.role_sets[category] = RoleSet(room_category=category, roles=roles)

    def get_role_set(self, room_category: str) -> RoleSet:
        """Get the role set for a specific room category."""
        return self.role_sets.get(room_category, RoleSet(room_category=room_category))

    def create_default_role_set(self, room_category: str, num_roles: int = 100) -> RoleSet:
        """Generate a default role set if none exists (for development)."""
        # This can be expanded later with real role definitions
        roles = []
        for i in range(num_roles):
            roles.append(Role(
                role_id=f"{room_category}_role_{i:03d}",
                name=f"Role {i:03d} - {room_category}",
                category=room_category,
                specialty=f"Specialty {i}",
                perspective="General specialized perspective",
                traits=["detail-oriented"],
                skills=["analysis"],
                prompt_template=f"You are Role {i} specializing in {room_category}. Evaluate and refine the work.",
                quality_criteria=["high quality", "thorough"]
            ))
        return RoleSet(room_category=room_category, roles=roles)
