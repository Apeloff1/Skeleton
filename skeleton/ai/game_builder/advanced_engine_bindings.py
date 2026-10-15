"""Bindings for existing original-game reference runtimes into the canonical studio.

These modules own simulation rules; this table only connects approved editor
identities to start, step, strict layout validation and source replay.
No provider calls, shell commands, downloaded assets or new execution root.
"""
from __future__ import annotations

from . import advanced_procedural_world_runtime as procedural_world_engine
from . import advanced_economy_runtime as economy_engine
from . import advanced_voxel_runtime as voxel_engine
from . import advanced_parkour_runtime as parkour_engine
from . import advanced_ecosystem_runtime as ecosystem_engine
from . import advanced_sports_runtime as sports_engine
from . import advanced_npc_society_runtime as npc_society_engine
from . import advanced_dialogue_runtime as dialogue_engine
from . import advanced_narrative_runtime as narrative_engine
from . import advanced_cinematics_runtime as cinematics_engine

MODULES = {
    "procedural_world": procedural_world_engine,
    "economy": economy_engine,
    "voxel": voxel_engine,
    "parkour": parkour_engine,
    "ecosystem": ecosystem_engine,
    "sports": sports_engine,
    "npc_society": npc_society_engine,
    "dialogue": dialogue_engine,
    "narrative": narrative_engine,
    "cinematics": cinematics_engine,
}
ACTIONS = {name: module.ACTIONS for name, module in MODULES.items()}
STARTS = {name: module.start for name, module in MODULES.items()}
STEPS = {name: module.step for name, module in MODULES.items()}
DEFAULT_LAYOUTS = {name: module.default_layout for name, module in MODULES.items()}
NORMALIZE_LAYOUTS = {name: module.normalize_layout for name, module in MODULES.items()}
APPLY_SCENES = {name: module.apply_scene for name, module in MODULES.items()}
ERRORS = (procedural_world_engine.ProceduralWorldActionError,
          economy_engine.EconomyActionError,
          voxel_engine.VoxelActionError,
          parkour_engine.ParkourActionError,
          ecosystem_engine.EcosystemActionError,
          sports_engine.SportsActionError,
          npc_society_engine.SocietyActionError,
          dialogue_engine.DialogueActionError,
          narrative_engine.NarrativeActionError,
          cinematics_engine.CinematicActionError,)

__all__ = ["MODULES", "ACTIONS", "STARTS", "STEPS", "DEFAULT_LAYOUTS",
           "NORMALIZE_LAYOUTS", "APPLY_SCENES", "ERRORS"]
