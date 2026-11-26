"""Ludonarrative dissonance investigation.
Definition, causes, and design countermeasures.
"""
from typing import Dict, Any

class LudonarrativeDissonance:
    def investigate(self) -> Dict[str, Any]:
        return {
            "definition": "Conflict between the narrative themes or character portrayal and the mechanics the player actually performs",
            "examples": {
                "violence": "Story condemns killing while gameplay rewards mass combat",
                "urgency": "Narrative claims time pressure while systems allow unlimited delay",
                "character": "Protagonist is portrayed as reluctant while player is incentivized to be aggressive"
            },
            "causes": [
                "Systems designed independently of story",
                "Reward structures that contradict stated themes",
                "Failure to make the want/need conflict mechanically felt"
            ],
            "countermeasures": {
                "harmony": "Design systems so playing them enacts the narrative themes",
                "alignment": "Ensure climax choice is mechanical, not only dialogic",
                "audit": "Review reward loops against stated want and need"
            },
            "investigated": True
        }
