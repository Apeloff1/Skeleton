"""Unified world-runtime seam for generated RPG/adventure playables.

Composes character progression, skill graph, weather contexts, NPC schedules,
creature AI, and versioned save integrity behind one deterministic runtime. The
frontend can render this state in Expo/web/native without owning domain rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.character_profile import CharacterProfile
from core.creature_ai import Creature, Stimulus
from core.environment_runtime import EnvironmentRuntime
from core.save_envelope import SaveCodec
from core.skill_graph import SkillGraph, SkillProfile
from core.world_agents import NavigationGraph, WorldAgent


@dataclass(frozen=True, slots=True)
class WorldTick:
    minute: int
    weather: str
    contexts: tuple[str, ...]
    agent_locations: dict[str, str]
    creature_states: dict[str, str]


class WorldRuntime:
    def __init__(
        self,
        *,
        graph: NavigationGraph,
        agents: list[WorldAgent],
        creatures: dict[str, Creature] | None = None,
        character: CharacterProfile | None = None,
        skill_graph: SkillGraph | None = None,
        environment: EnvironmentRuntime | None = None,
        save_version: int = 1,
    ) -> None:
        self.graph = graph
        self.agents = {agent.id: agent for agent in agents}
        if len(self.agents) != len(agents):
            raise ValueError("duplicate world-agent id")
        self.creatures = dict(creatures or {})
        self.character = character or CharacterProfile("Player")
        self.skill_graph = skill_graph
        self.skill_profile = SkillProfile()
        self.environment = environment or EnvironmentRuntime()
        self.minute = 0
        self.save_codec = SaveCodec(save_version)

    def tick(
        self,
        *,
        minutes: int = 1,
        dt: float = 1.0,
        stimuli: dict[str, list[Stimulus]] | None = None,
        seed: int | None = None,
    ) -> WorldTick:
        if minutes < 0:
            raise ValueError("minutes cannot be negative")
        if dt <= 0:
            raise ValueError("dt must be positive")
        self.minute = (self.minute + minutes) % (24 * 60)
        weather = self.environment.step(dt, seed=seed)
        contexts = self.environment.contexts()

        for agent in self.agents.values():
            agent.sync_schedule(self.graph, self.minute, contexts=contexts)
            agent.advance()

        creature_states: dict[str, str] = {}
        for index, (creature_id, creature) in enumerate(sorted(self.creatures.items())):
            state = creature.update(
                dt,
                (stimuli or {}).get(creature_id, ()),
                seed=None if seed is None else seed + index,
            )
            creature_states[creature_id] = state.value

        return WorldTick(
            minute=self.minute,
            weather=self.environment.current_weather,
            contexts=contexts,
            agent_locations={agent_id: agent.node_id for agent_id, agent in self.agents.items()},
            creature_states=creature_states,
        )

    def purchase_skill(self, skill_id: str) -> int:
        if self.skill_graph is None:
            raise ValueError("world runtime has no skill graph")
        return self.skill_graph.purchase(
            self.skill_profile,
            skill_id,
            player_level=self.character.level,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "minute": self.minute,
            "environment": {
                "current": self.environment.current_weather,
                "target": self.environment.target_weather,
                "state": asdict(self.environment.state),
            },
            "character": {
                "name": self.character.name,
                "stats": dict(self.character.stats),
                "skills": dict(self.character.skills),
                "inventory": dict(self.character.inventory),
                "currency": self.character.currency,
                "level": self.character.level,
                "experience": self.character.experience,
                "background_id": self.character.background_id,
            },
            "skill_profile": {
                "points": self.skill_profile.points,
                "levels": dict(self.skill_profile.levels),
            },
            "agents": {agent_id: agent.node_id for agent_id, agent in self.agents.items()},
            "creatures": {
                creature_id: {
                    "x": creature.x,
                    "y": creature.y,
                    "vx": creature.vx,
                    "vy": creature.vy,
                    "energy": creature.energy,
                    "hunger": creature.hunger,
                    "state": creature.state.value,
                }
                for creature_id, creature in self.creatures.items()
            },
        }

    def encode_save(self) -> str:
        return self.save_codec.encode(self.snapshot())
