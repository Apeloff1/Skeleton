"""Static project-settings checks (GFP-01..04)."""
from __future__ import annotations

from .project import GodotProject
from .report import CaseResult
from .version import feature_version

GF_SMOKE_TICKS = (30, 60)


def physics_ticks(project: GodotProject, allowed: tuple[int, ...] = GF_SMOKE_TICKS) -> CaseResult:
    t = project.physics_ticks
    return CaseResult("GFP-01", t in allowed, {"ticks": t, "allowed": list(allowed)})


def main_scene(project: GodotProject) -> CaseResult:
    m = project.main_scene
    if not m:
        return CaseResult("GFP-02", False, "application/run/main_scene not set")
    return CaseResult("GFP-02", project.exists(m), m)


def autoloads(project: GodotProject) -> CaseResult:
    missing = {k: v for k, v in project.autoloads.items() if not project.exists(v)}
    return CaseResult("GFP-03", not missing, missing or "all present")


def engine_feature(project: GodotProject) -> CaseResult:
    v = feature_version(project.features)
    return CaseResult("GFP-04", v is not None and v.major == 4, project.features)


def run_all(project: GodotProject, ticks: tuple[int, ...] = GF_SMOKE_TICKS) -> list[CaseResult]:
    return [physics_ticks(project, ticks), main_scene(project), autoloads(project), engine_feature(project)]
