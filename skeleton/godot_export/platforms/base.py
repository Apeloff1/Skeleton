"""Shared platform validator contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..presets import ExportPreset

OptionCheck = Callable[[ExportPreset], list[str]]
ArtifactCheck = Callable[[Path], list[str]]


@dataclass(frozen=True)
class PlatformSpec:
    name: str
    extensions: tuple[str, ...]
    option_checks: tuple[OptionCheck, ...] = field(default_factory=tuple)
    artifact_check: ArtifactCheck | None = None
    export_on_linux: bool = True

    def check_preset(self, preset: ExportPreset) -> list[str]:
        problems = []
        if self.extensions and not preset.export_path.lower().endswith(self.extensions):
            problems.append(f"export_path {preset.export_path!r} should end with one of {self.extensions}")
        for check in self.option_checks:
            problems.extend(check(preset))
        return problems

    def check_artifact(self, path: Path) -> list[str]:
        if not path.exists():
            return [f"artifact missing: {path}"]
        if path.is_file() and path.stat().st_size == 0:
            return [f"artifact empty: {path}"]
        return self.artifact_check(path) if self.artifact_check else []


def require_bool(key: str, expected: bool) -> OptionCheck:
    def check(p: ExportPreset) -> list[str]:
        v = p.option(key)
        if v is None:
            return []
        return [] if bool(v) == expected else [f"{key} should be {expected}"]
    return check


def require_in(key: str, allowed: tuple[object, ...], required: bool = False) -> OptionCheck:
    def check(p: ExportPreset) -> list[str]:
        v = p.option(key)
        if v is None:
            return [f"{key} missing"] if required else []
        return [] if v in allowed else [f"{key}={v!r} not in {allowed}"]
    return check


def require_pattern(key: str, pattern: str, required: bool = False) -> OptionCheck:
    import re
    rx = re.compile(pattern)

    def check(p: ExportPreset) -> list[str]:
        v = p.option(key)
        if v in (None, ""):
            return [f"{key} missing"] if required else []
        return [] if isinstance(v, str) and rx.fullmatch(v) else [f"{key}={v!r} does not match {pattern}"]
    return check


def read_head(path: Path, n: int = 64) -> bytes:
    with path.open("rb") as fh:
        return fh.read(n)
