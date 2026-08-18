"""
gameforge.godot_engine — First-class Godot engine integration for Tutolage.

The Godot editor binary ships in-repo at ``backend/godot`` (Linux x86_64,
~103 MB). This package turns that binary into a managed engine:

* :mod:`gameforge.godot_engine.binary`   — locate, verify, and probe the binary
* :mod:`gameforge.godot_engine.project`  — scaffold Godot projects (project.godot,
  scenes, GDScript) from structured specs
* :mod:`gameforge.godot_engine.pipeline` — run headless Godot jobs (import,
  export, script-check) as tracked async tasks

The HTTP surface lives in ``routes/godot_engine.py`` and is mounted at
``/api/godot-engine`` via ``core.routes_registry.KNOWN_ROUTES``.
"""

from gameforge.godot_engine.binary import GodotBinary, get_binary
from gameforge.godot_engine.project import ProjectSpec, scaffold_project
from gameforge.godot_engine.pipeline import GodotPipeline, get_pipeline

__all__ = [
    "GodotBinary",
    "get_binary",
    "ProjectSpec",
    "scaffold_project",
    "GodotPipeline",
    "get_pipeline",
]
