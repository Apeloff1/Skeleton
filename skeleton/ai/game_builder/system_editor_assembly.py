"""Assemble multiple reviewed, typed game system editors into one audited plan.

Compilation is deliberately separate from build/export. The returned graph
makes missing runtime adapters and product obligations explicit rather than
claiming that configuration documents are finished game engines.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Mapping, Sequence

from .system_editors import (
    CATALOG, PREVIEW_ACTIONS, ADVANCED_ENGINE_IDS, MINIMUM_PROGRESSION,
    SystemEditorError, validate_editor_document, preview_editor,
)
from .advanced_gameplay_runtime import run_advanced_session
from .advanced_level_scenes import validate_advanced_scene, scene_path

GROUP_ORDER = ("Product", "World", "Simulation", "Strategy", "Action", "Vehicle", "Creative")
EDGES = (
    ("physics", "platformer", "gravity_and_fixed_step"),
    ("platformer", "metroidvania", "traversal_unlocks"),
    ("procedural_world", "voxel", "chunk_terrain_payload"),
    ("procedural_world", "ecosystem", "biome_resource_carriage"),
    ("npc_society", "quest_director", "witnessed_event_activation"),
    ("npc_society", "dialogue", "speaker_memory"),
    ("npc_society", "economy", "finite_inventory"),
    ("npc_society", "colony", "labor_and_need_schedule"),
    ("farming", "economy", "crop_supply_chain"),
    ("factory", "economy", "production_inventory"),
    ("survival", "farming", "seasonal_resource_consumption"),
    ("rpg", "quest_director", "quest_and_postgame_persistence"),
    ("tactics", "rpg", "party_action_point_combat"),
    ("tactics", "deck_battler", "action_resource_exchange"),
    ("racing", "physics", "vehicle_collision_and_forces"),
    ("sailing", "physics", "buoyancy_and_currents"),
    ("flight", "physics", "lift_drag_stall"),
    ("shooter", "stealth", "detection_combat_transition"),
    ("animation", "cinematics", "shot_animation_tracks"),
    ("audio", "rhythm", "beat_schedule_and_sound_cues"),
    ("ui_hud", "accessibility", "remapping_and_legibility"),
    ("localization", "dialogue", "speaker_text_fallback"),
    ("save_system", "roguelike", "run_lifecycle"),
    ("save_system", "sandbox", "unbounded_world_persistence"),
    ("networking", "tactics", "turn_command_serialization"),
    ("platform_profile", "npc_society", "era_specific_active_budget"),
    ("platform_profile", "ui_hud", "device_input_budget"),
)
REQUIRED_REVIEW = (
    "originality_and_source_rights", "real_gameplay_quality",
    "save_and_replay_validation", "target_hardware_execution",
    "accessibility_and_localization", "publication_permission",
)


class AssemblyError(SystemEditorError):
    """An invalid source collection or cross-system compatibility envelope."""


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def compile_system_assembly(project_id: str,
                            documents: Sequence[object], *,
                            authorized: bool,
                            scenes: Sequence[object] = ()) -> dict:
    if not authorized:
        raise PermissionError("system-assembly review requires explicit local authority")
    if type(project_id) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", project_id):
        raise AssemblyError("invalid bounded original project identity")
    if type(documents) not in (list, tuple) or not 1 <= len(documents) <= len(CATALOG):
        raise AssemblyError("assembly requires one or more bounded reviewed editor documents")
    configs = {}
    for raw in documents:
        validated = validate_editor_document(raw)
        editor = validated["editor"]
        if editor in configs:
            raise AssemblyError("duplicate system editor cannot silently override configuration")
        configs[editor] = validated
    # These checks are meaningful composition constraints; a system can pass
    # its individual form and still fail a multi-system product budget.
    def settings(name):
        return configs[name]["settings"]
    if "npc_society" in configs and "platform_profile" in configs:
        npc = settings("npc_society"); platform = settings("platform_profile")
        if npc["active_npcs"] > platform["npc_active_budget"]:
            raise AssemblyError("active NPC simulation exceeds platform-era budget")
    if "npc_society" in configs and "dialogue" in configs:
        if settings("dialogue")["speakers"] > max(1, settings("npc_society")["population"]):
            raise AssemblyError("dialogue speaker count exceeds authored NPC population")
    if "physics" in configs and "platformer" in configs:
        # The reference platformer uses discrete 1-step gravity. A separately
        # configured rigid-body engine must not silently double or invert it.
        if abs(settings("physics")["gravity"] - settings("platformer")["gravity"]) > 2:
            raise AssemblyError("platformer and physics gravity presets diverge")
    if "networking" in configs:
        net = settings("networking")
        if net["authority"] == "local_only" and net["max_players"] != 1:
            raise AssemblyError("local-only networking cannot certify remote player count")
        if net["authority"] == "lockstep" and net["rollback_frames"] > 0:
            raise AssemblyError("lockstep and predictive rollback require a reviewed hybrid adapter")
    if "sandbox" in configs and "save_system" in configs:
        if settings("sandbox")["allow_perpetual_play"] and settings("save_system")["autosave_minutes"] == 0:
            raise AssemblyError("persistent sandbox needs nonzero autosave coverage")
    if "rhythm" in configs and "audio" in configs:
        if settings("audio")["channels"] < settings("audio")["dynamic_layers"]:
            raise AssemblyError("audio playback channels cannot underprovision rhythm layers")
    ordered = sorted(configs, key=lambda name: (
        GROUP_ORDER.index(next(spec["group"] for spec in CATALOG if spec["id"] == name)),
        name,
    ))
    edges = [
        {"source": source, "target": target, "contract": contract,
         "adapter_ready": False}
        for source, target, contract in EDGES
        if source in configs and target in configs
    ]
    snapshots = [
        {"editor": name, "source_digest": configs[name]["digest"],
         "progression_floor": MINIMUM_PROGRESSION,
         "preview_mode": (
             "advanced_playable_reference" if name in ADVANCED_ENGINE_IDS else
             "reference_prototype" if name in PREVIEW_ACTIONS else "authoring_only"
         ),
         "runtime_adapter_integrated": False}
        for name in ordered
    ]
    # Run all currently available prototype simulations against EXACT editor
    # settings and keep their independently reproducible evidence hashes.
    prototypes = [
        {"editor": name, "proof_digest": preview_editor(
            name, configs[name]["settings"])["digest"]}
        for name in ordered if name in PREVIEW_ACTIONS
    ]
    advanced_smoke = {
        "platformer": ("jump_right", "right", "wait"),
        "tactics": ("east", "end_turn"),
        "tower_defense": ("build:0", "tick:4"),
        "racing": ("accelerate", "accelerate", "coast"),
        "survival": ("forage", "drink", "rest"),
        "shooter": ("wait",),
        "deck_battler": ("end_turn",),
        "puzzle": ("wait",),
        "farming": ("advance",),
        "factory": ("tick",),
        "colony": ("tick",),
        "city_builder": ("tick",),
        "stealth": ("wait",),
        "metroidvania": ("inspect",),
    }
    if set(advanced_smoke) != set(ADVANCED_ENGINE_IDS):
        raise AssemblyError("every playable editor needs an explicit assembly gameplay proof")
    advanced_evidence = [
        {"editor": name,
         "gameplay_session_digest": run_advanced_session(
             name, configs[name]["settings"], advanced_smoke[name])["digest"],
         "advanced_floor_met_in_reference_runtime": True,
         "native_game_engine_certified": False}
        for name in ordered if name in ADVANCED_ENGINE_IDS
    ]
    if type(scenes) not in (tuple,list) or len(scenes)>64:
        raise AssemblyError("original authored scene collection must be bounded")
    scene_evidence=[]
    seen_scenes=set()
    for raw_scene in scenes:
        if type(raw_scene) is not dict:
            raise AssemblyError("reviewed scene must use an exact typed JSON contract")
        editor=raw_scene.get("editor")
        if editor not in configs:
            raise AssemblyError("authored scene has no approved parent editor settings")
        source=validate_advanced_scene(raw_scene,configs[editor]["settings"])
        path=scene_path(source)
        if path in seen_scenes:
            raise AssemblyError("duplicate authored scene identity in composite game")
        seen_scenes.add(path)
        # A custom scene can disable tower slot 0, begin with an exhausted
        # biome or place an obstacle at the default movement destination.
        # Use legal, side-effectful baseline steps that work independently of
        # tactical placement and resource availability; gameplay quality
        # still requires separate player/mirror review.
        scene_smoke={
            "platformer":("wait",),"tactics":("end_turn",),
            "tower_defense":("tick",),"racing":("coast",),
            "survival":("rest",),
            "shooter":("wait",),"deck_battler":("end_turn",),
            "puzzle":("wait",),
            "farming":("advance",),
            "factory":("tick",),
            "colony":("tick",),
            "city_builder":("tick",),
            "stealth":("wait",),
            "metroidvania":("inspect",),
        }
        if set(scene_smoke) != set(ADVANCED_ENGINE_IDS):
            raise AssemblyError("every playable editor needs a source-bound scene proof")
        proof=run_advanced_session(editor,configs[editor]["settings"],
                                   scene_smoke[editor],
                                   seed=source["seed"],scene=source)
        scene_evidence.append({
            "path":path,"editor":editor,"scene_digest":source["digest"],
            "settings_digest":source["settings_digest"],
            "gameplay_session_digest":proof["digest"],
            "release_certified":False,
        })
    scene_evidence.sort(key=lambda row:row["path"])
    payload = {
        "schema": "skeleton.game_builder.system_assembly.v1",
        "project": project_id, "source_system_count": len(ordered),
        "source_order": ordered, "systems": snapshots,
        "progression_floor": MINIMUM_PROGRESSION,
        "prototype_evidence": prototypes, "advanced_runtime_evidence":advanced_evidence,
        "authored_scene_count":len(scene_evidence),
        "authored_scene_evidence":scene_evidence,
        "coupling_edges": edges,
        "unresolved_runtime_adapters": ordered,
        "remaining_independent_reviews": list(REQUIRED_REVIEW),
        "source_mutated": False, "executed_external_tools": False,
        "ready_for_release": False,
    }
    return {**payload, "digest": _digest(payload)}


def assemble_workspace_systems(workspace: object, project: str, *,
                               authorized: bool) -> dict:
    """Compile ONLY the active, human-reviewed current workbench sources."""
    from .game_project_workspace import GameWorkspace
    if not authorized:
        raise PermissionError("assembly requires local designer authorization")
    if not isinstance(workspace, GameWorkspace) or workspace.active() != project:
        raise AssemblyError("system assembly must target the active reviewed current project")
    documents = []
    scenes=[]
    for record in workspace.files("current", project):
        if record.path.startswith("systems/"):
            try:
                document = json.loads(workspace.read(
                    "current", project, record.path)["content"])
            except (ValueError, UnicodeError) as exc:
                raise AssemblyError("invalid project system source") from exc
            expected_path = "systems/" + document.get("editor", "") + ".json" if type(document) is dict and type(document.get("editor")) is str else ""
            if record.path != expected_path:
                raise AssemblyError("workspace system path violates document identity")
            documents.append(document)
        elif record.path.startswith("scenes/advanced_"):
            try:
                scene=json.loads(workspace.read("current",project,record.path)["content"])
            except (ValueError, UnicodeError) as exc:
                raise AssemblyError("invalid authored scene source") from exc
            if type(scene) is not dict or record.path!=scene_path(scene):
                raise AssemblyError("authored scene has mismatched on-disk source identity")
            scenes.append(scene)
    return compile_system_assembly(project, documents, authorized=True, scenes=scenes)


__all__ = ["AssemblyError", "compile_system_assembly", "assemble_workspace_systems"]
