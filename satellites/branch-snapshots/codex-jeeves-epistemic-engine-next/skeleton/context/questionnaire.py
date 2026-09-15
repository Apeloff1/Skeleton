"""
Skeleton Context — Questionnaire and intake system

Provides:
- intake: Process structured answers into a game design vision
- Questionnaire: Interactive game design questionnaire
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IntakeResult:
    """Result of the game design intake questionnaire."""
    vision: str
    era: str = "extraction_now"
    genre: str = ""
    target_platform: str = "godot"
    answers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vision": self.vision,
            "era": self.era,
            "genre": self.genre,
            "target_platform": self.target_platform,
            "answers": self.answers,
        }


def intake(answers: Dict[str, Any]) -> IntakeResult:
    """Process questionnaire answers into a game design specification.
    
    Args:
        answers: Dict of question_id -> answer mappings
        
    Returns:
        IntakeResult with synthesized vision and era
    """
    # Extract key design parameters
    genre = answers.get("genre", "action-adventure")
    theme = answers.get("theme", "sci-fi")
    perspective = answers.get("perspective", "third-person")
    combat_style = answers.get("combat", "tactical")
    progression = answers.get("progression", "skill-tree")
    
    # Synthesize vision statement
    vision_parts = [
        f"A {perspective} {genre} game",
        f"set in a {theme} universe",
        f"with {combat_style} combat",
        f"and {progression} progression.",
    ]
    
    # Determine era from theme
    era_map = {
        "sci-fi": "extraction_now",
        "fantasy": "medieval_fantasy",
        "modern": "contemporary",
        "post-apocalyptic": "wasteland",
        "cyberpunk": "neon_dystopia",
    }
    era = era_map.get(theme, "extraction_now")
    
    return IntakeResult(
        vision=" ".join(vision_parts),
        era=era,
        genre=genre,
        target_platform=answers.get("target", "godot"),
        answers=answers,
    )


class Questionnaire:
    """Interactive game design questionnaire."""

    QUESTIONS = [
        {"id": "genre", "question": "What genre?", "options": ["action-adventure", "rpg", "strategy", "platformer", "simulation"]},
        {"id": "theme", "question": "What theme/setting?", "options": ["sci-fi", "fantasy", "modern", "post-apocalyptic", "cyberpunk"]},
        {"id": "perspective", "question": "Camera perspective?", "options": ["first-person", "third-person", "top-down", "isometric", "side-scrolling"]},
        {"id": "combat", "question": "Combat style?", "options": ["tactical", "real-time", "turn-based", "none", "puzzle-based"]},
        {"id": "progression", "question": "Progression system?", "options": ["skill-tree", "level-based", "equipment", "narrative", "open-ended"]},
    ]

    def __init__(self):
        self.answers: Dict[str, Any] = {}

    def ask(self, question_id: str, answer: Any) -> None:
        """Record an answer."""
        self.answers[question_id] = answer

    def complete(self) -> IntakeResult:
        """Finalize the questionnaire and return the intake result."""
        return intake(self.answers)

    def progress(self) -> Dict[str, Any]:
        """Return current completion status."""
        answered = set(self.answers.keys())
        total = len(self.QUESTIONS)
        return {
            "answered": len(answered),
            "total": total,
            "remaining": [q["id"] for q in self.QUESTIONS if q["id"] not in answered],
            "complete": len(answered) >= total,
        }
