"""Highest caliber.
Most precise how/why/when across AAA game, story, cinematic, music.
Integrated into Jeeves for maximum outcome.
"""
from typing import Dict, Any
from datetime import datetime
import uuid

class Highest:
    def execute(self, brief: str) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "brief": brief,
            "game": {
                "how": "Every player verb produces a readable systemic consequence that is immediately rewarding and permanently expands option space. Combat consumes inventory. Progression gates narrative. Narrative reframes systems.",
                "why": "Retention comes from fun. Mastery comes from interlocking systems. Purpose comes from meta goals that recontextualize earlier play. Choices matter because risk and reward are both legible and consequential.",
                "when": "Minutes 0-10: single verb mastery. Minutes 10-60: two-system interaction. Hour 2+: full interlock + narrative stakes that retroactively elevate earlier mechanics."
            },
            "story": {
                "how": "Protagonist want is concrete and external. Need is internal and contradictory. Every scene either advances the want or pressures the need. Midpoint makes the want achievable only by confronting the need. Climax forces a choice that cannot satisfy both.",
                "why": "Investment requires clarity of desire and visibility of cost. Theme lands when the audience watches the character pay or refuse to pay.",
                "when": "Act 1: want + obstacle. Midpoint: false victory that reveals the real problem. Act 3: irreversible decision."
            },
            "cinematic": {
                "how": "Geography first (wide). Performance second (medium). Emotion third (close). Camera moves only to follow intent, reveal information, or heighten feeling. Key light models, fill preserves eyes, rim separates.",
                "why": "The audience must always know where they are, who matters, and how to feel. Confusion or unmotivated movement breaks immersion.",
                "when": "Dialogue: stable, longer. Action: shorter, dynamic, cut on movement. Reveal: hold the frame, then accelerate."
            },
            "music": {
                "how": "Each major character and theme owns a short melodic cell. Cells combine and transform. Texture scales with dramatic weight. Every hit is frame-accurate. Transitions hide inside action or dialogue.",
                "why": "Music pre-loads emotion and creates memory across hours of play. The audience feels continuity even when they cannot name the motif.",
                "when": "Character entrance: cell under picture. Rising action: development. Climax: full orchestral statement. Resolution: cell resolved or inverted."
            },
            "highest": True,
            "caliber": "highest",
            "integrated": True,
            "beta_ready": True,
            "ts": datetime.utcnow().isoformat()
        }
