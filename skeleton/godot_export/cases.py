"""Certification case catalogue for Godot export + GF-D QA.

Each case has a stable id, a severity and the TODO items it traces to. Any
failing Sev1/Sev2 case makes a certification run NO-SHIP.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Severity(IntEnum):
    SEV1 = 1
    SEV2 = 2
    SEV3 = 3
    SEV4 = 4

    @property
    def blocking(self) -> bool:
        return self <= Severity.SEV2


@dataclass(frozen=True)
class Case:
    id: str
    severity: Severity
    title: str
    todo: tuple[str, ...] = ()


_RAW: tuple[Case, ...] = (
    Case("GFD-00", Severity.SEV1, "project.godot present and parseable", ("GF-P0-38",)),
    Case("GFD-01", Severity.SEV1, "headless --import exits 0 within budget", ("GF-P0-38", "GF-P0-74", "GF-P0-96")),
    Case("GFD-02", Severity.SEV1, "no ERROR / SCRIPT ERROR / Parse Error during import", ("GF-P0-38",)),
    Case("GFD-03", Severity.SEV2, "import produced the .godot/ cache", ("GF-P0-38",)),
    Case("GFD-04", Severity.SEV1, "every .gd passes --check-only", ("GF-P0-38",)),
    Case("GFD-05", Severity.SEV2, "every res:// reference resolves", ("GF-P0-38",)),
    Case("GFD-06", Severity.SEV3, "scripts and scenes were emitted", ("GF-P0-38",)),
    Case("GFX-01", Severity.SEV1, "export_presets.cfg present and parseable"),
    Case("GFX-02", Severity.SEV1, "every preset names a known platform"),
    Case("GFX-03", Severity.SEV2, "preset export_path set and relative to project"),
    Case("GFX-04", Severity.SEV2, "platform options valid for preset platform"),
    Case("GFX-05", Severity.SEV1, "headless --export-release exits 0"),
    Case("GFX-06", Severity.SEV1, "exported artifact exists with correct binary format"),
    Case("GFX-07", Severity.SEV2, "exported .pck header valid and non-empty"),
    Case("GFX-08", Severity.SEV3, "preset names unique"),
    Case("GFX-09", Severity.SEV2, "no secret-looking values in presets"),
    Case("GFL-01", Severity.SEV2, "GDScript lint: no mixed indentation"),
    Case("GFL-02", Severity.SEV3, "GDScript lint: extends/class_name ordering"),
    Case("GFL-03", Severity.SEV2, "GDScript lint: preload/load targets exist"),
    Case("GFL-04", Severity.SEV2, "GDScript lint: duplicate class_name across project"),
    Case("GFP-01", Severity.SEV2, "physics ticks per second is 30 or 60 for GF smoke", ("GF-P0-74",)),
    Case("GFP-02", Severity.SEV2, "main scene set and exists", ("GF-P0-38",)),
    Case("GFP-03", Severity.SEV2, "autoload targets exist"),
    Case("GFP-04", Severity.SEV3, "config/features declares a Godot 4.x version"),
    Case("GFS-01", Severity.SEV2, "RigidBody3D nodes declare positive mass", ("GF-P0-74",)),
    Case("GFS-02", Severity.SEV2, "SoftBody3D nodes declare positive total_mass and pinned points", ("GF-P0-96",)),
    Case("GFS-03", Severity.SEV3, "3D main scene has a current Camera3D", ("GF-P0-38",)),
    Case("GFB-01", Severity.SEV1, "Godot binary version matches pin", ("GF-P0-134",)),
    Case("GFB-02", Severity.SEV1, "Godot binary sha256 matches pin", ("GF-P0-134",)),
)

CASES: dict[str, Case] = {c.id: c for c in _RAW}


def get(case_id: str) -> Case:
    try:
        return CASES[case_id]
    except KeyError as exc:
        raise KeyError(f"unknown certification case {case_id}") from exc


def by_todo(todo_id: str) -> list[Case]:
    return [c for c in _RAW if todo_id in c.todo]


def todo_ids() -> list[str]:
    return sorted({t for c in _RAW for t in c.todo})
