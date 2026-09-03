"""Text-to-NPC pipeline: persona, dialogue trees, behaviour graphs.

Takes a natural-language description and materialises a complete NPC spec:
a persona card, a branching dialogue tree, and a behaviour graph that the
runtime can drive. Deterministic local synthesis is the default; a generator
callable can be injected for LLM-backed production.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from skeleton.kernel.errors import GenerationError, ValidationError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import PipelineRunId

GeneratorFn = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class DialogueNode:
    node_id: str
    speaker_line: str
    choices: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "line": self.speaker_line, "choices": list(self.choices)}


@dataclass(frozen=True)
class BehaviourState:
    name: str
    enter_action: str
    exit_action: str
    transitions: tuple[tuple[str, str], ...] = ()


@dataclass
class NpcSpec:
    run_id: str
    name: str
    archetype: str
    persona: dict[str, Any]
    dialogue_tree: list[DialogueNode]
    behaviour_graph: list[BehaviourState]
    generated_at: float = field(default_factory=time.time)
    quality: dict[str, Any] = field(default_factory=dict)
    quality_stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "archetype": self.archetype,
            "persona": self.persona,
            "dialogue_tree": [n.to_dict() for n in self.dialogue_tree],
            "behaviour_graph": [
                {"name": s.name, "enter": s.enter_action, "exit": s.exit_action,
                 "transitions": [[t, tgt] for t, tgt in s.transitions]}
                for s in self.behaviour_graph
            ],
            "generated_at": self.generated_at,
            "quality": dict(self.quality),
            "quality_stats": dict(self.quality_stats),
        }


_ARCHETYPES = ("mentor", "merchant", "rival", "companion", "trickster", "guardian")
_TRAIT_POOL = (
    "curious", "stoic", "sardonic", "warm", "calculating", "impulsive",
    "loyal", "secretive", "verbose", "terse", "optimistic", "paranoid",
)
_QUIRKS = (
    "always speaks in questions", "collects broken compasses",
    "never uses the protagonist's name", "hums when lying",
    "counts doorways obsessively",
)


def _seeded(description: str) -> int:
    return int(hashlib.sha256(description.encode()).hexdigest()[:16], 16)


def _default_generator(description: str, params: dict[str, Any]) -> dict[str, Any]:
    seed = _seeded(description)
    archetype = params.get("archetype") or _ARCHETYPES[seed % len(_ARCHETYPES)]
    n_traits = 2 + seed % 3
    traits = sorted({_TRAIT_POOL[(seed >> (4 * i)) % len(_TRAIT_POOL)] for i in range(n_traits)})
    return {
        "archetype": archetype,
        "traits": traits,
        "quirk": _QUIRKS[seed % len(_QUIRKS)],
        "motivation": f"Driven by the events described as: {description[:80]}",
        "speech_register": ["formal", "casual", "archaic"][seed % 3],
    }


def _build_dialogue(persona: dict[str, Any], beats: int) -> list[DialogueNode]:
    nodes: list[DialogueNode] = [DialogueNode("root", f"A {persona['traits'][0]} greeting in a {persona['speech_register']} register.")]
    for i in range(1, beats + 1):
        prev = nodes[-1]
        nodes[-1] = DialogueNode(prev.node_id, prev.speaker_line, prev.choices + (f"beat_{i}",))
        nodes.append(DialogueNode(f"beat_{i}", f"Beat {i}: {persona['archetype']} response driven by {persona['motivation'][:40]}"))
    last = nodes[-1]
    nodes[-1] = DialogueNode(last.node_id, last.speaker_line, last.choices + ("farewell",))
    nodes.append(DialogueNode("farewell", "A closing line consistent with the persona quirk."))
    return nodes


def _build_behaviour(archetype: str) -> list[BehaviourState]:
    return [
        BehaviourState("idle", "play_idle_anim", "stop_idle_anim", (("player_near", "greet"), ("threat", "alert"))),
        BehaviourState("greet", f"play_{archetype}_greet", "reset_greet", (("dialogue_end", "idle"), ("threat", "alert"))),
        BehaviourState("alert", "raise_weapon", "lower_weapon", (("threat_gone", "idle"),)),
    ]


class NpcPipeline:
    def __init__(self, bus: EventBus | None = None, generator: GeneratorFn | None = None, *, root=None) -> None:
        self._bus = bus or EventBus()
        self._generator = generator or _default_generator
        self._root = root

    def run(self, description: str, *, name: str | None = None,
            dialogue_beats: int = 3, params: dict[str, Any] | None = None) -> NpcSpec:
        from skeleton.intelligence.npc_verifier import NpcVerifier
        from skeleton.organism.quality_state import append_quality

        if not description or not description.strip():
            raise ValidationError("NPC description must be non-empty")
        if not 1 <= dialogue_beats <= 12:
            raise ValidationError("dialogue_beats must be in [1, 12]",
                                  context={"dialogue_beats": dialogue_beats})
        run_id = str(PipelineRunId.new())
        start = self._bus.emit("pipeline.npc.started",
                               {"run_id": run_id, "description": description[:120]})
        try:
            persona = self._generator(description, dict(params or {}))
            if "archetype" not in persona or "traits" not in persona:
                raise GenerationError("generator returned an incomplete persona",
                                      context={"keys": sorted(persona)})
            spec = NpcSpec(
                run_id=run_id,
                name=name or f"npc_{run_id[-6:]}",
                archetype=persona["archetype"],
                persona=persona,
                dialogue_tree=_build_dialogue(persona, dialogue_beats),
                behaviour_graph=_build_behaviour(persona["archetype"]),
            )
        except (ValidationError, GenerationError):
            raise
        except Exception as exc:
            raise GenerationError("NPC generation failed", cause=exc,
                                  context={"run_id": run_id}) from exc

        verifier = NpcVerifier()
        quality = verifier.verify(spec.to_dict(), description=description)
        spec.quality = quality.to_dict()
        spec.quality_stats = verifier.stats()
        append_quality({
            "kind": "quality",
            "surface": "npc",
            "accepted": quality.accepted,
            "reason": quality.reason,
            "score": quality.score,
            "weakest_path": quality.weakest_path,
            "summary": quality.summary,
            "metadata": quality.quality.metadata,
        }, root=self._root)
        self._bus.publish(DomainEvent(
            topic="pipeline.npc.quality",
            payload={
                "run_id": run_id,
                "name": spec.name,
                "accepted": quality.accepted,
                "reason": quality.reason,
                "score": quality.score,
                "weakest_path": quality.weakest_path,
            },
            correlation_id=start.correlation_id,
            causation_id=start.event_id,
        ))
        self._bus.emit("pipeline.npc.completed",
                       {"run_id": run_id, "name": spec.name, "archetype": spec.archetype},
                       correlation_id=start.correlation_id, causation_id=start.event_id)
        return spec
