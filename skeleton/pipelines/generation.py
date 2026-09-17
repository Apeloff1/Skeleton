"""
Skeleton Pipelines — High-level task pipelines

Provides:
- NPCPipeline: Generate NPC specifications
- GameLogicPipeline: Design game mechanics
- AnimationPipeline: Create animation specifications

Every outward creation is passed through Jeeves' tri-engine adversarial quality
boundary: quality + adversarial quality + integrity, 100 gates per lane.
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
    speculative_rag: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "dialogue_beats": self.dialogue_beats,
            "personality_traits": self.personality_traits,
            "params": self.params,
            "speculative_rag": dict(self.speculative_rag),
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
    speculative_rag: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "max_level": self.max_level,
            "curve": self.curve,
            "currency": self.currency,
            "mechanics": self.mechanics,
            "progression": self.progression,
            "speculative_rag": dict(self.speculative_rag),
        }


@dataclass
class AnimationSpec:
    """Generated animation specification."""
    description: str
    actions: List[str] = field(default_factory=list)
    skeleton_type: str = "humanoid"
    transitions: List[Dict[str, str]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    speculative_rag: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "actions": self.actions,
            "skeleton_type": self.skeleton_type,
            "transitions": self.transitions,
            "params": self.params,
            "speculative_rag": dict(self.speculative_rag),
        }


def _release(request: str, candidate: Any, creation_type: str) -> Any:
    # Keep the heavy cortex package out of ordinary pipeline imports. The
    # release boundary is loaded only when a generated artifact is returned.
    from skeleton.cortex.tri_adversarial import guard_tri_creation

    return guard_tri_creation(
        request=request,
        candidate=candidate,
        metadata={"creation_type": creation_type},
    )


class NPCPipeline:
    """Generate NPC specifications from descriptions."""

    def __init__(self, genesis: Any = None) -> None:
        self._genesis = genesis

    def run(
        self,
        description: str,
        name: Optional[str] = None,
        dialogue_beats: int = 3,
        params: Optional[Dict[str, Any]] = None,
    ) -> NPCSpec:
        """Generate and tri-engine validate an NPC specification."""
        from skeleton.pipelines.speculative_rag import planning_prefetch_dict

        prefetch = planning_prefetch_dict(
            self._genesis,
            "npc",
            {"description": description},
            limit=3,
        )
        beats = [f"Beat {i+1}: {description[:20]}..." for i in range(dialogue_beats)]
        spec = NPCSpec(
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
            speculative_rag=prefetch,
        )
        return _release(description, spec, "npc")


class GameLogicPipeline:
    """Design game mechanics and progression systems."""

    def __init__(self, genesis: Any = None) -> None:
        self._genesis = genesis

    def run(
        self,
        description: str,
        title: str = "untitled",
        max_level: int = 50,
        curve: str = "quadratic",
        currency: str = "gold",
    ) -> GameLogicSpec:
        """Generate and tri-engine validate a game-logic specification."""
        from skeleton.pipelines.speculative_rag import planning_prefetch_dict

        prefetch = planning_prefetch_dict(
            self._genesis,
            "game_logic",
            {"description": description},
            limit=3,
        )
        mechanics = [
            {"name": "combat", "type": "turn_based", "description": description[:30]},
            {"name": "progression", "type": "level_up", "max_level": max_level},
            {"name": "economy", "type": "currency", "currency": currency},
        ]

        if curve == "linear":
            progression = [{"level": i, "xp_required": i * 100} for i in range(1, max_level + 1)]
        elif curve == "exponential":
            progression = [{"level": i, "xp_required": int(100 * (1.5 ** i))} for i in range(1, max_level + 1)]
        else:
            progression = [{"level": i, "xp_required": i * i * 50} for i in range(1, max_level + 1)]

        spec = GameLogicSpec(
            title=title,
            max_level=max_level,
            curve=curve,
            currency=currency,
            mechanics=mechanics,
            progression=progression[:10],
            speculative_rag=prefetch,
        )
        return _release(description, spec, "game_logic")


class AnimationPipeline:
    """Create animation specifications."""

    def __init__(self, genesis: Any = None) -> None:
        self._genesis = genesis

    def run(self, description: str, actions: Optional[tuple] = None) -> AnimationSpec:
        """Generate and tri-engine validate an animation specification."""
        from skeleton.pipelines.speculative_rag import planning_prefetch_dict

        prefetch = planning_prefetch_dict(
            self._genesis,
            "animation",
            {"description": description},
            limit=3,
        )
        default_actions = actions or ("idle", "walk", "run", "attack")
        transitions = []
        for i in range(len(default_actions) - 1):
            transitions.append({
                "from": default_actions[i],
                "to": default_actions[i + 1],
                "duration": 0.3,
                "blend": "smooth",
            })

        spec = AnimationSpec(
            description=description,
            actions=list(default_actions),
            skeleton_type="humanoid",
            transitions=transitions,
            params={
                "fps": 60,
                "root_motion": True,
                "ik_enabled": False,
            },
            speculative_rag=prefetch,
        )
        return _release(description, spec, "animation")
