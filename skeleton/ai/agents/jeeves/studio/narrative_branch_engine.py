"""Narrative branch engine.
Selects branches and endings from optical, salvage, and boss state.
"""
from typing import Any, Dict

class NarrativeBranchEngine:
    BRANCHES = ["standard", "high_optical", "rich_extract", "failure"]

    def select(self, optical: float, salvage: int, boss_defeated: bool) -> Dict[str, Any]:
        if not boss_defeated:
            branch = "failure"
        elif optical > 0.93 and salvage > 40:
            branch = "rich_extract"
        elif optical > 0.9:
            branch = "high_optical"
        else:
            branch = "standard"
        return {
            "branch": branch,
            "optical": optical,
            "salvage": salvage,
            "boss_defeated": boss_defeated,
            "schema": "skeleton.narrative.branch.v1",
        }
