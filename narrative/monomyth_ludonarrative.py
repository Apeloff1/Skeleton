"""Heroic Journey monomyth and ludonarrative harmony integration.
"""
from typing import Dict, Any

class MonomythLudonarrative:
    def monomyth(self) -> Dict[str, Any]:
        return {
            "departure": {
                "call_to_adventure": "Inciting disruption of ordinary world",
                "refusal": "Debate or hesitation mechanics",
                "supernatural_aid": "Mentor, item, or new verb",
                "threshold": "Break into Act 2 / new area"
            },
            "initiation": {
                "road_of_trials": "Fun and games + rising challenges",
                "meeting_with_goddess": "B Story relationship",
                "ordeal": "Midpoint or All Is Lost",
                "reward": "New capability or revelation"
            },
            "return": {
                "road_back": "Bad guys close in",
                "resurrection": "Finale / irreversible choice",
                "return_with_elixir": "Final image / changed equilibrium"
            },
            "mapped": True
        }

    def ludonarrative_harmony(self) -> Dict[str, Any]:
        return {
            "principle": "Mechanics and narrative express the same themes and emotional beats",
            "how": "Systems (inventory, combat, progression) are designed so that playing them enacts the want/need conflict",
            "examples": {
                "want": "Combat and exploration systems directly serve the external goal",
                "need": "Resource constraints or timing windows force confrontation with the internal flaw",
                "climax": "The irreversible choice is expressed through a mechanical decision, not only dialogue"
            },
            "harmony": True,
            "integrated_with_monomyth": True
        }
