"""Static, read-only typed Jeeves tools for original-world authoring.

These tools are safe to expose to a model planner: they cannot mutate
custody, approve original content, or claim an unverified game compile.
Operator writes remain exclusively in the reviewed CLI workflow.
"""
from __future__ import annotations

from typing import Any

from .evidence import EvidenceStore, propose_evidence
from .factions import FactionStore, propose_factions
from .promises import PromiseStore, propose_promises, prove_promises
from .context_journal import ContextStore
from .knowledge import KnowledgeStore, propose_knowledge, prove_knowledge
from .cast import CastStore
from .session import SessionStore
from .migration import preview_migration
from .playtest import prove_choice_coverage
from .choice_impact import analyze_choice_impact
from .scenario import ScenarioStore
from .invariants import InvariantStore
from .assurance import AssuranceStore
from .atlas import AtlasStore
from .portals import PortalStore
from .npc_schedule import ScheduleStore
from .inventory import InventoryStore
from .puzzles import PuzzleStore
from .events import EventStore
from .relationships import RelationshipStore
from .testimony import TestimonyStore
from .rumors import RumorStore
from .localization import LocalizationStore
from .accessibility import AccessibilityStore
from .director import DirectorStore
from .chapters import ChapterStore
from .cinematics import CinematicsStore
from .pacing import PacingStore
from .studio_assembly import StudioAssemblyStore
from .studio_engine import StudioEngineStore
from .economy import EconomyStore
from .character_arcs import ArcStore
from .dialogue_graph import DialogueStore
from .interaction_assembly import InteractionStore
from .dialogue_transcript import DialogueTranscriptStore
from .dialogue_localization import DialogueLocaleStore
from .epilogues import EpilogueStore
from .advisories import AdvisoryStore
from .weather import WeatherStore
from .field_journal import FieldJournalStore
from .branching import ForkStore
from .laptop_flow import LaptopFlow
from .revision import analyze_revision
from .world_canon import (
    CanonError, WorldStore, _id, _keys, canonical, digest, propose, prove, strict_json,
)

SCHEMA = "jeeves.world.tool_request.v1"
RESULT_SCHEMA = "jeeves.world.tool_result.v1"

TOOLS = {
    "world.laptop_propose_preview": ("premise", "protagonist", "region", "goal"),
    "world.laptop_preview": (),
    "world.laptop_handoff_preview": (),
    "world.proof": (),
    "world.playtest_preview": (),
    "world.choice_impact_preview": (),
    "world.scenario_preview": (),
    "world.invariants_preview": (),
    "world.assurance_preview": (),
    "world.atlas_preview": (),
    "world.relationships_player": ("slot",),
    "world.dialogue_locales_preview": (),
    "world.dialogue_locales_propose_preview": (
        "prompt", "tag", "conversation_id", "node_id", "text",
        "response_id", "label",
    ),
    "world.dialogue_transcript_preview": ("slot",),
    "world.interaction_preview": (),
    "world.dialogue_preview": (),
    "world.dialogue_player": ("slot", "conversation", "responses"),
    "world.dialogue_propose_preview": (
        "prompt", "conversation_id", "actor", "scene", "text",
        "response_id", "label", "world_choice",
    ),
    "world.character_arcs_preview": (),
    "world.character_arcs_player": ("slot",),
    "world.character_arcs_propose_preview": (
        "prompt", "actor", "desire", "starting_belief",
        "resolved_belief", "choice", "text",
    ),
    "world.economy_preview": (),
    "world.economy_player": ("slot",),
    "world.economy_propose_preview": (
        "prompt", "resource_id", "name", "initial", "capacity",
        "choice_id", "cost", "gain",
    ),
    "world.studio_engine_preview": ("era",),
    "world.studio_preview": (),
    "world.studio_player": ("slot", "locale"),
    "world.director_preview": (),
    "world.director_player": ("slot",),
    "world.chapters_preview": (),
    "world.chapters_propose_preview": ("prompt", "chapters"),
    "world.chapters_player": ("slot",),
    "world.cinematics_preview": (),
    "world.cinematics_propose_preview": ("prompt", "sequences"),
    "world.cinematics_player": ("slot",),
    "world.pacing_preview": (),
    "world.pacing_propose_preview": ("prompt", "beats"),
    "world.pacing_player": ("slot",),
    "world.accessibility_preview": (),
    "world.accessibility_propose_preview": ("prompt", "scenes", "choices", "endings"),
    "world.accessibility_player": ("slot",),
    "world.localization_preview": (),
    "world.localization_propose_preview": ("prompt", "locale"),
    "world.localization_player": ("slot", "locale"),
    "world.rumors_preview": (),
    "world.rumors_propose_preview": (
        "prompt", "rumor_id", "claim", "stance", "origin", "seed_choice", "text",
    ),
    "world.rumors_player": ("slot",),
    "world.testimony_preview": (),
    "world.testimony_propose_preview": (
        "prompt", "statement_id", "actor", "scene", "choice", "claim",
        "stance", "text", "provenance",
    ),
    "world.testimony_player": ("slot",),
    "world.relationships_preview": (),
    "world.relationships_propose_preview": (
        "prompt", "bond_id", "actor", "name", "choice", "delta", "reason",
        "reaction_id", "scene", "min_score", "max_score", "text",
    ),
    "world.events_preview": (),
    "world.events_propose_preview": (
        "prompt", "event_id", "scene", "description", "requires", "grants",
    ),
    "world.puzzles_preview": (),
    "world.puzzles_propose_preview": (
        "prompt", "puzzle_id", "scene", "question", "answer", "hint", "unlock_choice",
    ),
    "world.inventory_preview": (),
    "world.inventory_propose_preview": (
        "prompt", "item_id", "name", "description", "pickup_choice",
    ),
    "world.npc_schedule_preview": (),
    "world.npc_schedule_propose_preview": (
        "prompt", "actor", "scene", "first_tick", "last_tick", "label",
    ),
    "world.portals_preview": ("network_id",),
    "world.portals_session_preview": ("network_id", "session"),
    "world.portals_propose_preview": ("network_id", "prompt", "from_ending", "to_world"),
    "world.atlas_propose_preview": ("prompt",),
    "world.field_journal_preview": ("slot",),
    "world.field_journal_propose_preview": ("slot", "note_id", "text"),
    "world.advisories_preview": (),
    "world.weather_preview": (),
    "world.weather_player": ("slot",),
    "world.weather_propose_preview": ("prompt", "scenes", "overrides"),
    "world.advisories_propose_preview": ("prompt", "entries"),
    "world.advisories_player": ("slot",),
    "world.epilogues_preview": (),
    "world.epilogues_player": ("slot",),
    "world.epilogues_propose_preview": ("prompt", "entries"),
    "world.fork_preview": ("parent_slot", "target_slot", "prompt", "at_revision", "choice_id"),
    "world.fork_inspect": ("target_slot",),
    "world.fork_compare": ("target_slot",),
    "world.revision_preview": ("old_world",),
    "world.migration_preview": ("old_world", "checkpoint", "choice_map"),
    "knowledge.propose_preview": (
        "prompt", "fact_id", "title", "detail", "choice", "speaker", "recipient",
    ),
    "knowledge.inspect": (),
    "knowledge.proof": (),
    "knowledge.player": ("slot",),
    "context.status": (),
    "promises.propose_preview": (
        "prompt", "promise_id", "title", "setup", "payoff",
        "trigger_choice", "resolve_choice", "required",
    ),
    "promises.inspect": (),
    "promises.proof": (),
    "promises.player": ("slot",),
    "factions.propose_preview": (
        "prompt", "faction_id", "name", "description",
        "choice_id", "delta", "reason",
    ),
    "factions.inspect": (),
    "factions.player": ("slot",),
    "evidence.propose_preview": (
        "prompt", "clue_id", "title", "detail", "unlock_choice",
    ),
    "evidence.inspect": (),
    "evidence.player": ("slot",),
}


def manifest() -> dict[str, Any]:
    return {
        "schema": "jeeves.world.tool_manifest.v1",
        "tools": [
            {"name": name, "required_args": list(TOOLS[name]),
             "read_only": True, "operator_write_required": True}
            for name in sorted(TOOLS)
        ],
        "authority": "read_only_no_mutation_or_implicit_approval",
    }


def invoke_world_tool(root: str, request: Any) -> dict[str, Any]:
    req = _keys(request, {"schema", "tool", "world_id", "args"})
    if req["schema"] != SCHEMA:
        raise CanonError("world_tool_schema_mismatch")
    name = req["tool"]
    if type(name) is not str or name not in TOOLS:
        raise CanonError("unknown_world_tool")
    _id(req["world_id"], "world_id")
    args = _keys(req["args"], set(TOOLS[name]))
    world = (propose(world_id=req["world_id"], **args)
             if name == "world.laptop_propose_preview"
             else WorldStore(root).read(req["world_id"]))
    if name == "world.laptop_propose_preview":
        payload = {"world": world, "proof": prove(world).as_dict(),
                   "review_required": True, "persisted": False}
    elif name == "world.laptop_preview":
        payload = LaptopFlow(root).inspect(req["world_id"])
    elif name == "world.laptop_handoff_preview":
        payload = LaptopFlow(root).verify(req["world_id"])
    elif name == "world.weather_propose_preview":
        payload = WeatherStore(root).propose(req["world_id"], **args)
    elif name == "world.weather_preview":
        payload = WeatherStore(root).inspect(req["world_id"])
    elif name == "world.weather_player":
        payload = WeatherStore(root).player(req["world_id"], args["slot"])
    elif name == "world.field_journal_propose_preview":
        payload = FieldJournalStore(root).preview(req["world_id"], **args)
    elif name == "world.field_journal_preview":
        payload = FieldJournalStore(root).inspect(req["world_id"], args["slot"])
    elif name == "world.advisories_propose_preview":
        payload = AdvisoryStore(root).propose(req["world_id"], **args)
    elif name == "world.advisories_preview":
        payload = AdvisoryStore(root).inspect(req["world_id"])
    elif name == "world.advisories_player":
        payload = AdvisoryStore(root).player(req["world_id"], args["slot"])
    elif name == "world.epilogues_propose_preview":
        payload = EpilogueStore(root).propose(req["world_id"], **args)
    elif name == "world.epilogues_preview":
        payload = EpilogueStore(root).inspect(req["world_id"])
    elif name == "world.epilogues_player":
        payload = EpilogueStore(root).player(req["world_id"], args["slot"])
    elif name == "world.fork_preview":
        payload = ForkStore(root).preview(req["world_id"], **args)
    elif name == "world.fork_inspect":
        payload = ForkStore(root).inspect(req["world_id"], args["target_slot"])
    elif name == "world.fork_compare":
        payload = ForkStore(root).compare(req["world_id"], args["target_slot"])
    elif name == "world.revision_preview":
        payload = analyze_revision(args["old_world"], world)
    elif name == "world.playtest_preview":
        payload = prove_choice_coverage(world)
    elif name == "world.choice_impact_preview":
        payload = analyze_choice_impact(world)
    elif name == "world.scenario_preview":
        payload = ScenarioStore(root).inspect(req["world_id"])["report"]
    elif name == "world.invariants_preview":
        payload = InvariantStore(root).inspect(req["world_id"])["report"]
    elif name == "world.relationships_propose_preview":
        payload = RelationshipStore(root).propose(req["world_id"], **args)
    elif name == "world.relationships_player":
        _id(args["slot"], "slot")
        payload = RelationshipStore(root).player(req["world_id"], args["slot"])
    elif name == "world.dialogue_locales_propose_preview":
        payload = DialogueLocaleStore(root).propose(req["world_id"], **args)
    elif name == "world.dialogue_locales_preview":
        payload = DialogueLocaleStore(root).inspect(req["world_id"])
    elif name == "world.dialogue_transcript_preview":
        _id(args["slot"], "slot")
        payload = DialogueTranscriptStore(root).inspect(req["world_id"], args["slot"])
    elif name == "world.interaction_preview":
        payload = InteractionStore(root).inspect(req["world_id"])
    elif name == "world.dialogue_propose_preview":
        payload = DialogueStore(root).propose(req["world_id"], **args)
    elif name == "world.dialogue_preview":
        payload = DialogueStore(root).inspect(req["world_id"])
    elif name == "world.dialogue_player":
        _id(args["slot"], "slot")
        payload = DialogueStore(root).player(
            req["world_id"], args["slot"], args["conversation"], args["responses"])
    elif name == "world.character_arcs_propose_preview":
        payload = ArcStore(root).propose(req["world_id"], **args)
    elif name == "world.character_arcs_preview":
        payload = ArcStore(root).inspect(req["world_id"])
    elif name == "world.character_arcs_player":
        _id(args["slot"], "slot")
        payload = ArcStore(root).player(req["world_id"], args["slot"])
    elif name == "world.economy_propose_preview":
        payload = EconomyStore(root).propose(req["world_id"], **args)
    elif name == "world.economy_preview":
        payload = EconomyStore(root).inspect(req["world_id"])
    elif name == "world.economy_player":
        _id(args["slot"], "slot")
        payload = EconomyStore(root).player(req["world_id"], args["slot"])
    elif name == "world.studio_engine_preview":
        payload = StudioEngineStore(root).inspect(req["world_id"], args["era"])
    elif name == "world.studio_preview":
        payload = StudioAssemblyStore(root).inspect(req["world_id"])
    elif name == "world.studio_player":
        _id(args["slot"], "slot")
        payload = StudioAssemblyStore(root).player(req["world_id"], args["slot"], args["locale"])
    elif name == "world.pacing_propose_preview":
        payload = PacingStore(root).propose(req["world_id"], **args)
    elif name == "world.cinematics_propose_preview":
        payload = CinematicsStore(root).propose(req["world_id"], **args)
    elif name == "world.chapters_propose_preview":
        payload = ChapterStore(root).propose(req["world_id"], **args)
    elif name == "world.director_preview":
        payload = DirectorStore(root).inspect(req["world_id"])
    elif name == "world.director_player":
        _id(args["slot"], "slot")
        payload = DirectorStore(root).player(req["world_id"], args["slot"])
    elif name == "world.chapters_preview":
        payload = ChapterStore(root).inspect(req["world_id"])
    elif name == "world.chapters_player":
        _id(args["slot"], "slot")
        payload = ChapterStore(root).player(req["world_id"], args["slot"])
    elif name == "world.cinematics_preview":
        payload = CinematicsStore(root).inspect(req["world_id"])
    elif name == "world.cinematics_player":
        _id(args["slot"], "slot")
        payload = CinematicsStore(root).player(req["world_id"], args["slot"])
    elif name == "world.pacing_preview":
        payload = PacingStore(root).inspect(req["world_id"])
    elif name == "world.pacing_player":
        _id(args["slot"], "slot")
        payload = PacingStore(root).player(req["world_id"], args["slot"])
    elif name == "world.accessibility_propose_preview":
        payload = AccessibilityStore(root).propose(req["world_id"], **args)
    elif name == "world.accessibility_preview":
        payload = AccessibilityStore(root).inspect(req["world_id"])
    elif name == "world.accessibility_player":
        _id(args["slot"], "slot")
        payload = AccessibilityStore(root).player(req["world_id"], args["slot"])
    elif name == "world.localization_propose_preview":
        payload = LocalizationStore(root).propose(req["world_id"], **args)
    elif name == "world.localization_preview":
        payload = LocalizationStore(root).inspect(req["world_id"])
    elif name == "world.localization_player":
        _id(args["slot"], "slot")
        payload = LocalizationStore(root).player(req["world_id"], args["slot"], args["locale"])
    elif name == "world.rumors_propose_preview":
        payload = RumorStore(root).propose(req["world_id"], **args)
    elif name == "world.rumors_preview":
        payload = RumorStore(root).inspect(req["world_id"])
    elif name == "world.rumors_player":
        _id(args["slot"], "slot")
        payload = RumorStore(root).player(req["world_id"], args["slot"])
    elif name == "world.testimony_propose_preview":
        payload = TestimonyStore(root).propose(req["world_id"], **args)
    elif name == "world.testimony_preview":
        payload = TestimonyStore(root).inspect(req["world_id"])
    elif name == "world.testimony_player":
        _id(args["slot"], "slot")
        payload = TestimonyStore(root).player(req["world_id"], args["slot"])
    elif name == "world.relationships_preview":
        payload = RelationshipStore(root).inspect(req["world_id"])
    elif name == "world.events_propose_preview":
        payload = EventStore(root).propose(req["world_id"], **args)
    elif name == "world.events_preview":
        payload = EventStore(root).inspect(req["world_id"])
    elif name == "world.puzzles_propose_preview":
        payload = PuzzleStore(root).propose(req["world_id"], **args)
    elif name == "world.puzzles_preview":
        payload = PuzzleStore(root).inspect(req["world_id"])
    elif name == "world.inventory_propose_preview":
        payload = InventoryStore(root).propose(req["world_id"], **args)
    elif name == "world.inventory_preview":
        payload = InventoryStore(root).inspect(req["world_id"])
    elif name == "world.npc_schedule_propose_preview":
        payload = ScheduleStore(root).propose(req["world_id"], **args)
    elif name == "world.npc_schedule_preview":
        payload = ScheduleStore(root).inspect(req["world_id"])
    elif name == "world.portals_propose_preview":
        payload = PortalStore(root).propose(
            args["network_id"], args["prompt"], root_world=req["world_id"],
            from_ending=args["from_ending"], to_world=args["to_world"],
        )
    elif name == "world.portals_session_preview":
        portal_store = PortalStore(root)
        inspected = portal_store.inspect(args["network_id"])
        if inspected["network"]["root_world"] != req["world_id"]:
            raise CanonError("portals_root_world_mismatch")
        payload = portal_store.preview_session(args["network_id"], args["session"])
    elif name == "world.portals_preview":
        payload = PortalStore(root).inspect(args["network_id"])
        if payload["network"]["root_world"] != req["world_id"]:
            raise CanonError("portals_root_world_mismatch")
    elif name == "world.atlas_preview":
        payload = AtlasStore(root).inspect(req["world_id"])
    elif name == "world.atlas_propose_preview":
        payload = AtlasStore(root).propose(req["world_id"], args["prompt"])
    elif name == "world.assurance_preview":
        payload = AssuranceStore(root).preview(req["world_id"])
    elif name == "world.migration_preview":
        payload = preview_migration(args["old_world"], args["checkpoint"], world,
                                    args["choice_map"])
    elif name == "world.proof":
        payload = prove(world).as_dict()
    elif name == "knowledge.propose_preview":
        cast = CastStore(root).read(req["world_id"])
        payload = propose_knowledge(world, cast, **args)
    elif name == "knowledge.inspect":
        payload = KnowledgeStore(root).read(req["world_id"])
    elif name == "knowledge.proof":
        cast = CastStore(root).read(req["world_id"])
        payload = prove_knowledge(
            KnowledgeStore(root).read(req["world_id"]), world, cast)
    elif name == "knowledge.player":
        _id(args["slot"], "slot")
        session = SessionStore(root).read(req["world_id"], args["slot"])
        payload = KnowledgeStore(root).player(
            req["world_id"], session["choices"])
    elif name == "context.status":
        payload = ContextStore(root).status(req["world_id"])
    elif name == "promises.propose_preview":
        payload = propose_promises(world, **args)
    elif name == "promises.inspect":
        payload = PromiseStore(root).read(req["world_id"])
    elif name == "promises.proof":
        payload = prove_promises(PromiseStore(root).read(req["world_id"]), world)
    elif name == "promises.player":
        _id(args["slot"], "slot")
        payload = PromiseStore(root).player(req["world_id"], args["slot"])
    elif name == "factions.propose_preview":
        payload = propose_factions(world, **args)
    elif name == "factions.inspect":
        payload = FactionStore(root).read(req["world_id"])
    elif name == "factions.player":
        _id(args["slot"], "slot")
        payload = FactionStore(root).player(req["world_id"], args["slot"])
    elif name == "evidence.propose_preview":
        payload = propose_evidence(world, **args)
    elif name == "evidence.inspect":
        payload = EvidenceStore(root).read(req["world_id"])
    elif name == "evidence.player":
        _id(args["slot"], "slot")
        payload = EvidenceStore(root).player(req["world_id"], args["slot"])
    else:
        raise CanonError("unknown_world_tool")
    # Detach the result from mutable store-backed Python objects.
    output = strict_json(canonical(payload))
    return {
        "schema": RESULT_SCHEMA, "tool": name, "world_id": world["id"],
        "world_digest": digest(world), "result_digest": digest(output),
        "result": output, "persisted": False, "review_required": (
            name.endswith("propose_preview")),
        "authority": "read_only_no_mutation",
    }
