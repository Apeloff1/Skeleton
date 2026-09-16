"""
gameforge.godot_engine — First-class Godot engine integration for Tutolage.

The Godot editor binary is artifact-plane (`docs/ARTIFACT_PLANE.md`).
Git tracks ``backend/godot.artifact.json`` only.
"""

from gameforge.godot_engine import binary as _bin
from gameforge.godot_engine.binary import GodotBinary, binary_status, get_binary
from gameforge.godot_engine.cache import TTLCache, engine_cache
from gameforge.godot_engine.health import HealthReport, deep_health
from gameforge.godot_engine.pipeline import GodotPipeline, get_pipeline
from gameforge.godot_engine.project import ProjectSpec, scaffold_project

locate = getattr(_bin, "locate", binary_status)

__all__ = [
    "GodotBinary",
    "get_binary",
    "locate",
    "binary_status",
    "TTLCache",
    "engine_cache",
    "HealthReport",
    "deep_health",
    "GodotPipeline",
    "get_pipeline",
    "ProjectSpec",
    "scaffold_project",
]
