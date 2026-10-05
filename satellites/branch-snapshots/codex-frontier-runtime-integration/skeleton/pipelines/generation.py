"""
Skeleton Pipelines — High-level task pipelines

Provides:
- NPCPipeline: Generate NPC specifications
- GameLogicPipeline: Design game mechanics
- AnimationPipeline: Create animation specifications
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NPCSpec:
    """Generated NPC specification."""
    name: str
    description: str
    dialogue_beats: List[str] = field(default_factory=list)
    personality_traits: Dict[str, float] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "dialogue_beats": self.dialogue_beats,
            "personality_traits": self.personality_traits,
            "params": self.params,
        }


@dataclass
class GameLogicSpec:
    """Generated game logic specification."""
    title: str
    max_level: int
    curve: str
    currency: str
    mechanics: List[Dict[str, Any]] = field(default_factory=list)
    progression: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "max_level": self.max_level,
            "curve": self.curve,
            "currency": self.currency,
            "mechanics": self.mechanics,
            "progression": self.progression,
        }


@dataclass
class AnimationSpec:
    """Generated animation specification."""
    description: str
    actions: List[str] = field(default_factory=list)
    skeleton_type: str = "humanoid"
    transitions: List[Dict[str, str]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "actions": self.actions,
            "skeleton_type": self.skeleton_type,
            "transitions": self.transitions,
            "params": self.params,
        }


class NPCPipeline:
    """Generate NPC specifications from descriptions."""

    def run(self, description: str, name: Optional[str] = None, dialogue_beats: int = 3, params: Optional[Dict[str, Any]] = None) -> NPCSpec:
        """Generate an NPC specification."""
        beats = [f"Beat {i+1}: {description[:20]}..." for i in range(dialogue_beats)]
        
        return NPCSpec(
            name=name or "Unnamed NPC",
            description=description,
            dialogue_beats=beats,
            personality_traits={
                "openness": 0.7,
                "conscientiousness": 0.5,
                "extraversion": 0.6,
                "agreeableness": 0.8,
                "neuroticism": 0.3,
            },
            params=params or {},
        )


class GameLogicPipeline:
    """Design game mechanics and progression systems."""

    def run(self, description: str, title: str = "untitled", max_level: int = 50, curve: str = "quadratic", currency: str = "gold") -> GameLogicSpec:
        """Generate game logic specification."""
        mechanics = [
            {"name": "combat", "type": "turn_based", "description": description[:30]},
            {"name": "progression", "type": "level_up", "max_level": max_level},
            {"name": "economy", "type": "currency", "currency": currency},
        ]

        # Generate progression curve
        if curve == "linear":
            progression = [{"level": i, "xp_required": i * 100} for i in range(1, max_level + 1)]
        elif curve == "exponential":
            progression = [{"level": i, "xp_required": int(100 * (1.5 ** i))} for i in range(1, max_level + 1)]
        else:  # quadratic
            progression = [{"level": i, "xp_required": i * i * 50} for i in range(1, max_level + 1)]

        return GameLogicSpec(
            title=title,
            max_level=max_level,
            curve=curve,
            currency=currency,
            mechanics=mechanics,
            progression=progression[:10],  # Truncate for brevity
        )


class AnimationPipeline:
    """Create animation specifications."""

    def run(self, description: str, actions: Optional[tuple] = None) -> AnimationSpec:
        """Generate animation specification."""
        default_actions = actions or ("idle", "walk", "run", "attack")
        
        transitions = []
        for i in range(len(default_actions) - 1):
            transitions.append({
                "from": default_actions[i],
                "to": default_actions[i + 1],
                "duration": 0.3,
                "blend": "smooth",
            })

        return AnimationSpec(
            description=description,
            actions=list(default_actions),
            skeleton_type="humanoid",
            transitions=transitions,
            params={
                "fps": 60,
                "root_motion": True,
                "ik_enabled": False,
            },
        )
