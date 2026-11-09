"""Godot export + GF-D QA certification toolkit.

Pure-Python parsers and validators for Godot 4 projects (``project.godot``,
``export_presets.cfg``, ``.tscn`` scenes, GDScript sources, ``.pck`` packs and
exported artifacts) plus thin, injectable runners around the real Godot
binary for headless import, ``--check-only`` parsing and preset export.

Everything that does not need the engine is testable offline; everything that
needs the engine goes through :class:`skeleton.godot_export.runner.GodotRunner`
so tests can substitute a fake process.
"""
from __future__ import annotations

from .cases import CASES, Case, Severity
from .report import CaseResult, CertificationReport

__all__ = ["CASES", "Case", "Severity", "CaseResult", "CertificationReport"]
