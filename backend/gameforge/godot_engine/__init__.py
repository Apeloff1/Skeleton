"""
gameforge.godot_engine — First-class Godot engine integration for Tutolage.

The Godot editor binary is artifact-plane (`docs/ARTIFACT_PLANE.md`).
Git tracks ``backend/godot.artifact.json`` only.
This package turns it into a managed engine, one focused module per concern:

* ``binary``     — locate, verify, and profile the binary (async probe)
* ``cache``      — TTL cache with stale-while-revalidate for engine metadata
* ``logbuffer``  — per-job ring log capture
* ``scheduler``  — staggered queue with bounded concurrency
* ``pipeline``   — headless jobs (import / check / export) as tracked tasks
* ``project``    — scaffold runnable Godot 4 projects from structured specs
* ``scenes``     — .tscn scene generators (platformer / topdown / empty)
* ``controllers``— playable GDScript player controllers
* ``presets``    — export presets (desktop / web / mobile)
* ``health``     — deep health snapshot for probes and readiness gates

HTTP surface: ``routes/godot_engine.py``, mounted at ``/api/godot-engine``
via ``core.routes_registry.KNOWN_ROUTES`` (group: ``engines``).
"""

from gameforge.godot_engine.binary import GodotBinary, binary_status, get_binary, locate
from gameforge.godot_engine.cache import TTLCache, engine_cache
from gameforge.godot_engine.health import HealthReport, deep_health
from gameforge.godot_engine.pipeline import GodotPipeline, get_pipeline
from gameforge.godot_engine.project import ProjectSpec, scaffold_project

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
