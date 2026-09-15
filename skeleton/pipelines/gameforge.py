"""
Skeleton GameForge — end-to-end game generation orchestrator.

The orchestration boundary now compiles questionnaire intent into a validated
GameCreationPlan before Forge materialisation.  That plan drives a type-safe
runtime graph, emitter build hints, NPC/logic context and play-test metadata.

The final packaged creation crosses Jeeves' tri-engine 3x100 release boundary
in addition to the component-level pipeline guards.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.cortex.tri_adversarial import guard_tri_creation
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.pipelines.game_creation import GameCreationPlan, GameCreationPlanner


@dataclass
class GameSpec:
    """Packaged game generation result."""

    spec_id: str
    title: str
    vision: str
    era: str
    blueprint_id: str
    genre: str = "action"
    creation_plan: Dict[str, Any] = field(default_factory=dict)
    creation_assessment: Dict[str, Any] = field(default_factory=dict)
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
            "genre": self.genre,
            "blueprint_id": self.blueprint_id,
            "creation_plan": self.creation_plan,
            "creation_assessment": self.creation_assessment,
            "npcs": self.npcs,
            "game_logic": self.game_logic,
            "animation": self.animation,
            "file_count": self.artefact.get("file_count", 0),
            "created_at": self.created_at,
        }


class GameForge:
    """Orchestrate full game generation from intake answers."""

    def __init__(self, genesis: Optional[Any] = None, bus: Optional[EventBus] = None):
        self._genesis = genesis
        self._bus = bus or (genesis.bus if genesis else EventBus())
        self._creator = GameCreationPlanner()
        self._stats = {"runs": 0, "failures": 0}

    def intake(self, answers: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw questionnaire answers into a structured intake."""
        from skeleton.context import intake as process_intake
        result = process_intake(answers)
        return result.to_dict()

    def run(self, answers: Dict[str, Any], title: Optional[str] = None,
            target: str = "json", repair: bool = False) -> GameSpec:
        """Run intake -> design planning -> Forge -> domain generation.

        ``repair`` remains the emitter verification/repair switch. Structural
        design repair runs before materialisation on every request.
        """
        from skeleton.context import intake as process_intake

        self._stats["runs"] += 1
        run_id = str(uuid.uuid4())[:8]

        try:
            intake_result = process_intake(answers)
            genre = self._creator.infer_genre(answers, intake_result.era)
            game_title = title or f"{genre.title()} of {intake_result.era.replace('_', ' ').title()}"
            creation = self._creator.create(
                intake=intake_result,
                answers=answers,
                title=game_title,
            )
            if not creation.assessment.ok:
                raise ValueError(
                    "game creation plan failed structural assessment: "
                    + "; ".join(creation.assessment.errors)
                )

            forge = self._get_forge()
            bp = self._build_blueprint(forge, creation.plan)
            artefact = forge.materialise(
                bp,
                era=intake_result.era,
                target=target,
                build_plan=creation.plan.to_build_plan(),
                repair=repair,
            )

            npcs = self._generate_npcs(creation.plan, game_title)
            game_logic = self._generate_logic(intake_result, creation.plan, game_title)
            animation = self._generate_animation(answers)

            spec = GameSpec(
                spec_id=run_id,
                title=game_title,
                vision=intake_result.vision,
                era=intake_result.era,
                genre=creation.plan.genre,
                blueprint_id=bp.blueprint_id,
                creation_plan=creation.plan.to_dict(),
                creation_assessment=creation.assessment.to_dict(),
                artefact=artefact,
                npcs=npcs,
                game_logic=game_logic,
                animation=animation,
            )
            released = guard_tri_creation(
                request=str(creation.plan.fantasy or intake_result.vision or game_title),
                candidate=spec,
                metadata={
                    "creation_type": "game_spec",
                    "target": target,
                    "genre": creation.plan.genre,
                    "scope": creation.plan.scope,
                    "planner_repair_rounds": creation.repair_rounds,
                    "repair_requested": bool(repair),
                },
            )

            self._bus.publish(DomainEvent(
                topic="gameforge.run.completed",
                payload={
                    "spec_id": run_id,
                    "title": game_title,
                    "target": target,
                    "genre": creation.plan.genre,
                    "scope": creation.plan.scope,
                },
                correlation_id=f"gameforge_{run_id}",
            ))
            return released

        except Exception as e:
            self._stats["failures"] += 1
            self._bus.publish(DomainEvent(
                topic="gameforge.run.failed",
                payload={"spec_id": run_id, "error": str(e)},
                correlation_id=f"gameforge_{run_id}",
            ))
            raise

    def _build_blueprint(self, forge: Any, plan: GameCreationPlan) -> Any:
        """Compile plan systems into an event-typed, acyclic Forge graph."""
        bp = forge.new_blueprint(plan.title)
        forge.instantiate(
            bp,
            "player",
            "hero",
            config={"verbs": list(plan.player_verbs), "perspective": plan.perspective},
        )
        previous = ("hero", "intent")

        for system in plan.systems:
            if system.name == "player_control":
                continue
            component_id = self._safe_id(system.name)
            if system.name == "encounter_director":
                forge.instantiate(
                    bp,
                    "enemy_spawner",
                    component_id,
                    config={"purpose": system.purpose, "acceptance": system.acceptance},
                )
                bp.connect(previous, (component_id, "tick"))
                previous = (component_id, "spawn")
                continue

            forge.instantiate(
                bp,
                "transform",
                component_id,
                config={
                    "purpose": system.purpose,
                    "depends_on": list(system.depends_on),
                    "acceptance": system.acceptance,
                },
            )
            bp.connect(previous, (component_id, "in"))
            previous = (component_id, "out")

        forge.instantiate(
            bp,
            "sink",
            "game_output",
            config={
                "core_loop": list(plan.core_loop),
                "playtests": [probe.to_dict() for probe in plan.playtests],
            },
        )
        bp.connect(previous, ("game_output", "in"))

        problems = bp.validate()
        if problems:
            raise ValueError("planner produced invalid Forge graph: " + "; ".join(problems))
        return bp

    @staticmethod
    def _safe_id(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value.lower())
        cleaned = cleaned.strip("_") or "system"
        return f"system_{cleaned}"

    def _get_forge(self) -> Any:
        if self._genesis is not None:
            forge = self._genesis.handles.get("forge")
            if forge is not None:
                return forge
        from skeleton.forge.universal import Forge
        return Forge(bus=self._bus)

    def _generate_npcs(self, plan: GameCreationPlan, title: str) -> List[Dict[str, Any]]:
        from skeleton.pipelines import NPCPipeline
        pipeline = NPCPipeline()
        roles = [
            ("guide", f"A {plan.genre} guide who teaches the first meaningful choice in {title}"),
            ("rival", f"A rival who pressures the core loop of {title} without bypassing player agency"),
        ]
        return [pipeline.run(desc, name=name.title()).to_dict() for name, desc in roles]

    def _generate_logic(self, intake_result: Any, plan: GameCreationPlan,
                        title: str) -> Dict[str, Any]:
        from skeleton.pipelines import GameLogicPipeline
        pipeline = GameLogicPipeline()
        request = (
            f"{intake_result.vision}. Player fantasy: {plan.fantasy}. "
            f"Core loop: {' -> '.join(plan.core_loop)}. "
            f"Player verbs: {', '.join(plan.player_verbs)}."
        )
        return pipeline.run(request, title=title).to_dict()

    def _generate_animation(self, answers: Dict[str, Any]) -> Dict[str, Any]:
        from skeleton.pipelines import AnimationPipeline
        pipeline = AnimationPipeline()
        perspective = answers.get("perspective", "third-person")
        return pipeline.run(f"{perspective} humanoid").to_dict()

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
