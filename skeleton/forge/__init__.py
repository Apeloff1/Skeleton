"""The Universal Forge — blueprints, validation, materialisers, accessors."""

from skeleton.forge.accessors import Accessor
from skeleton.forge.eras import blend_eras, compile_era, compile_pack, era_pack, list_eras
from skeleton.forge.hardware import catalog as hardware_catalog, detect_generation, get_generation, list_generations
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.sim import simulate_session, simulate_encounter
from skeleton.forge.walk import walk_graph, walk_from_pack
from skeleton.forge.projector import write_project, ProjectExistsError
from skeleton.forge.gdscript_check import check_files, check_ok
from skeleton.forge.world import generate_rooms, assert_connected
from skeleton.forge.planner import MaterialisationPlanner, BuildPlan
from skeleton.forge.archetypes import Archetype, ArchetypeError, ArchetypeLibrary, default_library
from skeleton.forge.diagram import to_dot
from skeleton.forge.materialisers import Materialiser, MaterialisationRegistry
from skeleton.forge.repair import latest_repair_plan, candidate_failures, attempt_repair
from skeleton.forge.universal import Blueprint, Component, Forge, Port, Wire
from skeleton.forge.validator import (
    CompositeValidator,
    Severity,
    ValidationProblem,
    ValidationReport,
    ValidationRule,
    default_validator,
)

__all__ = [
    "Accessor",
    "blend_eras",
    "compile_era",
    "compile_pack",
    "era_pack",
    "list_eras",
    "hardware_catalog",
    "detect_generation",
    "get_generation",
    "list_generations",
    "emit_godot",
    "simulate_session",
    "simulate_encounter",
    "walk_graph",
    "walk_from_pack",
    "write_project",
    "ProjectExistsError",
    "check_files",
    "check_ok",
    "generate_rooms",
    "assert_connected",
    "MaterialisationPlanner",
    "BuildPlan",
    "Archetype",
    "ArchetypeError",
    "ArchetypeLibrary",
    "default_library",
    "to_dot",
    "Materialiser",
    "MaterialisationRegistry",
    "latest_repair_plan",
    "candidate_failures",
    "attempt_repair",
    "Blueprint",
    "Component",
    "Forge",
    "Port",
    "Wire",
    "CompositeValidator",
    "Severity",
    "ValidationProblem",
    "ValidationReport",
    "ValidationRule",
    "default_validator",
]
