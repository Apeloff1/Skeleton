"""Unified world-runtime seam for generated RPG/adventure playables.

Composes character progression, skill graph, weather contexts, NPC schedules,
creature AI, relationships, travel/discovery, achievements, economy, dialogue,
and versioned save integrity behind one deterministic runtime. Frontends render
state; domain rules remain authoritative here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.achievement_engine import AchievementEngine, AchievementUnlock
from core.character_profile import CharacterProfile
from core.creature_ai import Creature, Stimulus
from core.dialogue_runtime import DialogueContext, DialogueRuntime
from core.discovery_engine import DiscoveryEngine, DiscoveryResult
from core.economy_runtime import EconomyRuntime, Inventory, PurchaseReceipt, Wallet
from core.environment_runtime import EnvironmentRuntime
from core.relationship_memory import RelationshipMemory
from core.save_envelope import SaveCodec
from core.skill_graph import SkillGraph, SkillProfile
from core.travel_graph import TravelGraph, TravelPlan
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
        travel_graph: TravelGraph | None = None,
        discovery_engine: DiscoveryEngine | None = None,
        achievement_engine: AchievementEngine | None = None,
        economy: EconomyRuntime | None = None,
        wallet: Wallet | None = None,
        economy_inventory: Inventory | None = None,
        dialogues: dict[str, DialogueRuntime] | None = None,
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
        self.travel_graph = travel_graph
        self.discovery_engine = discovery_engine
        self.achievement_engine = achievement_engine
        self.economy = economy
        self.wallet = wallet or Wallet()
        self.economy_inventory = economy_inventory or Inventory()
        self.dialogues = dict(dialogues or {})
        self.relationships: dict[str, RelationshipMemory] = {}
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
        self.environment.step(dt, seed=seed)
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

    def purchase_item(
        self,
        item_id: str,
        *,
        quantity: int = 1,
        price_multiplier: float = 1.0,
    ) -> PurchaseReceipt:
        if self.economy is None:
            raise ValueError("world runtime has no economy")
        return self.economy.purchase(
            item_id=item_id,
            quantity=quantity,
            player_level=self.character.level,
            wallet=self.wallet,
            inventory=self.economy_inventory,
            price_multiplier=price_multiplier,
        )

    def relationship(self, npc_id: str) -> RelationshipMemory:
        if npc_id not in self.agents:
            raise KeyError(f"unknown world agent: {npc_id}")
        memory = self.relationships.get(npc_id)
        if memory is None:
            memory = RelationshipMemory(npc_id)
            self.relationships[npc_id] = memory
        return memory

    def dialogue_context(self, npc_id: str) -> DialogueContext:
        memory = self.relationship(npc_id)
        return DialogueContext(
            relationship=memory.relationship,
            currency=self.wallet.balances.get("coins", 0),
            stats=dict(self.character.stats),
            inventory=dict(self.economy_inventory.items),
            unlocks=set(self.economy_inventory.unlocks),
        )

    def choose_dialogue(self, npc_id: str, node_id: str, choice_id: str):
        try:
            dialogue = self.dialogues[npc_id]
        except KeyError as exc:
            raise ValueError(f"world runtime has no dialogue for {npc_id}") from exc
        context = self.dialogue_context(npc_id)
        memory = self.relationship(npc_id)
        before_relationship = context.relationship
        outcome = dialogue.choose(node_id, choice_id, context)
        relationship_delta = context.relationship - before_relationship
        if relationship_delta:
            memory.record("dialogue", impact=relationship_delta, detail={"choice": choice_id})
        self.wallet.balances["coins"] = context.currency
        self.economy_inventory.items = dict(context.inventory)
        self.economy_inventory.unlocks = set(context.unlocks)
        return outcome

    def discover_location(self, location_id: str) -> bool:
        if self.travel_graph is None:
            raise ValueError("world runtime has no travel graph")
        return self.travel_graph.discover(location_id)

    def plan_travel(
        self,
        start: str,
        end: str,
        *,
        tags: tuple[str, ...] = (),
        danger_weight: float = 1.0,
        discovered_only: bool = False,
    ) -> TravelPlan:
        if self.travel_graph is None:
            raise ValueError("world runtime has no travel graph")
        return self.travel_graph.plan(
            start,
            end,
            level=self.character.level,
            tags=tags,
            danger_weight=danger_weight,
            discovered_only=discovered_only,
        )

    def evaluate_discoveries(self, facts: Mapping[str, Any] | None = None) -> DiscoveryResult:
        if self.discovery_engine is None:
            raise ValueError("world runtime has no discovery engine")
        merged: dict[str, Any] = {
            "player": {
                "level": self.character.level,
                "experience": self.character.experience,
                "currency": self.character.currency,
            },
            "world": {
                "weather": self.environment.current_weather,
                "minute": self.minute,
            },
        }
        if facts:
            merged.update(facts)
        return self.discovery_engine.evaluate(merged)

    def record_metric(self, metric: str, amount: float = 1.0) -> tuple[AchievementUnlock, ...]:
        if self.achievement_engine is None:
            raise ValueError("world runtime has no achievement engine")
        return self.achievement_engine.increment(metric, amount)

    def snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {
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
            "economy": EconomyRuntime.snapshot(self.wallet, self.economy_inventory),
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
            "relationships": {
                npc_id: memory.snapshot() for npc_id, memory in sorted(self.relationships.items())
            },
        }
        if self.travel_graph is not None:
            result["travel"] = {"discovered": sorted(self.travel_graph.discovered)}
        if self.discovery_engine is not None:
            result["discoveries"] = self.discovery_engine.snapshot()
        if self.achievement_engine is not None:
            result["achievements"] = self.achievement_engine.snapshot()
        return result

    def encode_save(self) -> str:
        return self.save_codec.encode(self.snapshot())
