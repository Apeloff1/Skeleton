"""The Universal Forge: composable blueprint synthesis + validation + diagrams."""

from skeleton.forge.archetypes import Archetype, ArchetypeError, ArchetypeLibrary, default_library
from skeleton.forge.diagram import to_dot
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
    "Archetype",
    "ArchetypeError",
    "ArchetypeLibrary",
    "default_library",
    "to_dot",
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
