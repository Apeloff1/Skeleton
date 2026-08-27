"""The Universal Forge — blueprints, validation, materialisers, accessors."""

from skeleton.forge.accessors import Accessor
from skeleton.forge.eras import compile_era, era_pack, list_eras
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.sim import simulate_session, simulate_encounter
from skeleton.forge.projector import write_project, ProjectExistsError
from skeleton.forge.gdscript_check import check_files, check_ok
from skeleton.forge.planner import MaterialisationPlanner, BuildPlan
from skeleton.forge.archetypes import Archetype, ArchetypeError, ArchetypeLibrary, default_library
from skeleton.forge.diagram import to_dot
from skeleton.forge.materialisers import Materialiser, MaterialisationRegistry
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
    "compile_era",
    "era_pack",
    "list_eras",
    "emit_godot",
    "simulate_session",
    "simulate_encounter",
    "write_project",
    "ProjectExistsError",
    "check_files",
    "check_ok",
    "MaterialisationPlanner",
    "BuildPlan",
    "Archetype",
    "ArchetypeError",
    "ArchetypeLibrary",
    "default_library",
    "to_dot",
    "Materialiser",
    "MaterialisationRegistry",
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
