"""
Skeleton GameForge — End-to-end game generation orchestrator

Ties the full pipeline together:

    questionnaire answers → IntakeResult → Blueprint → materialise
        → NPC/GameLogic/Animation specs → packaged game spec

Provides:
- GameForge: Orchestrator for intake → blueprint → pipelines
- GameSpec: Packaged output artifact
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class GameSpec:
    """Packaged game generation result."""
    spec_id: str
    title: str
    vision: str
    era: str
    blueprint_id: str
    artefact: Dict[str, Any] = field(default_factory=dict)
    npcs: List[Dict[str, Any]] = field(default_factory=list)
    game_logic: Optional[Dict[str, Any]] = None
    animation: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "title": self.title,
            "vision": self.vision,
            "era": self.era,
            "blueprint_id": self.blueprint_id,
            "npcs": self.npcs,
            "game_logic": self.game_logic,
            "animation": self.animation,
            "file_count": self.artefact.get("file_count", 0),
            "created_at": self.created_at,
        }


class GameForge:
    """Orchestrate full game generation from intake answers.

    Usage:
        forge = GameForge(genesis)
        spec = forge.run({"genre": "rpg", "theme": "fantasy", ...})
    """

    def __init__(self, genesis: Optional[Any] = None, bus: Optional[EventBus] = None):
        self._genesis = genesis
        self._bus = bus or (genesis.bus if genesis else EventBus())
        self._stats = {"runs": 0, "failures": 0}

    def intake(self, answers: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw questionnaire answers into a structured intake."""
        from skeleton.context import intake as process_intake
        result = process_intake(answers)
        return result.to_dict()

    def run(self, answers: Dict[str, Any], title: Optional[str] = None,
            target: str = "json", repair: bool = False) -> GameSpec:
        """Run the full game generation pipeline.

        Args:
            answers: Questionnaire answers (genre, theme, perspective, ...)
            title: Optional game title (defaults to derived name)
            target: Materialization target (json | godot)
            repair: Run verify-until-green loop for godot targets
        """
        from skeleton.context import intake as process_intake
        from skeleton.forge.universal import Forge

        self._stats["runs"] += 1
        run_id = str(uuid.uuid4())[:8]

        try:
            # 1. Intake → vision + era
            intake_result = process_intake(answers)
            game_title = title or f"{intake_result.genre.title()} of {intake_result.era.replace('_', ' ').title()}"

            # 2. Build blueprint from archetype
            forge = self._get_forge()
            bp = forge.new_blueprint(game_title)
            forge.instantiate(bp, "player", "hero")
            forge.instantiate(bp, "enemy_spawner", "spawner")
            forge.instantiate(bp, "weapon_forge", "weapons")
            forge.instantiate(bp, "extract", "goal")
            bp.connect(("hero", "intent"), ("spawner", "tick"))
            bp.connect(("hero", "intent"), ("weapons", "parts"))
            bp.connect(("spawner", "spawn"), ("goal", "cores"))

            # 3. Materialise
            artefact = forge.materialise(
                bp, era=intake_result.era, target=target, repair=repair,
            )

            # 4. Generate content pipelines
            npcs = self._generate_npcs(intake_result, game_title)
            game_logic = self._generate_logic(intake_result, game_title)
            animation = self._generate_animation(answers)

            spec = GameSpec(
                spec_id=run_id,
                title=game_title,
                vision=intake_result.vision,
                era=intake_result.era,
                blueprint_id=bp.blueprint_id,
                artefact=artefact,
                npcs=npcs,
                game_logic=game_logic,
                animation=animation,
            )

            self._bus.publish(DomainEvent(
                topic="gameforge.run.completed",
                payload={"spec_id": run_id, "title": game_title, "target": target},
                correlation_id=f"gameforge_{run_id}",
            ))
            return spec

        except Exception as e:
            self._stats["failures"] += 1
            self._bus.publish(DomainEvent(
                topic="gameforge.run.failed",
                payload={"spec_id": run_id, "error": str(e)},
                correlation_id=f"gameforge_{run_id}",
            ))
            raise

    def _get_forge(self) -> Any:
        if self._genesis is not None:
            forge = self._genesis.handles.get("forge")
            if forge is not None:
                return forge
        from skeleton.forge.universal import Forge
        return Forge(bus=self._bus)

    def _generate_npcs(self, intake_result: Any, title: str) -> List[Dict[str, Any]]:
        from skeleton.pipelines import NPCPipeline
        pipeline = NPCPipeline()
        roles = [
            ("quest giver", f"A {intake_result.genre} quest giver in the world of {title}"),
            ("rival", f"A rival who challenges the player in {title}"),
        ]
        return [pipeline.run(desc, name=name.title()).to_dict() for name, desc in roles]

    def _generate_logic(self, intake_result: Any, title: str) -> Dict[str, Any]:
        from skeleton.pipelines import GameLogicPipeline
        pipeline = GameLogicPipeline()
        return pipeline.run(intake_result.vision, title=title).to_dict()

    def _generate_animation(self, answers: Dict[str, Any]) -> Dict[str, Any]:
        from skeleton.pipelines import AnimationPipeline
        pipeline = AnimationPipeline()
        perspective = answers.get("perspective", "third-person")
        return pipeline.run(f"{perspective} humanoid").to_dict()

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
