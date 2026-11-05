"""``export_presets.cfg`` model (GFX-01..04, 08, 09)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import configfile

_PRESET = re.compile(r"^preset\.(\d+)$")
SECRET_KEY = re.compile(r"(password|passwd|secret|token|api_key|keystore/.*_password|encryption_key)", re.I)


@dataclass
class ExportPreset:
    index: int
    name: str
    platform: str
    export_path: str
    runnable: bool = False
    export_filter: str = "all_resources"
    include_filter: str = ""
    exclude_filter: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)

    @property
    def export_path_is_relative(self) -> bool:
        if not self.export_path:
            return False
        p = PurePosixPath(self.export_path.replace("\\", "/"))
        return not p.is_absolute() and ".." not in p.parts and not re.match(r"^[A-Za-z]:", self.export_path)


class PresetError(ValueError):
    pass


def from_config(cfg: configfile.ConfigFile) -> list[ExportPreset]:
    out = []
    for section in cfg.sections:
        m = _PRESET.match(section)
        if not m:
            continue
        idx = int(m.group(1))
        raw = cfg.sections[section]
        opts = cfg.sections.get(f"{section}.options", {})
        out.append(ExportPreset(
            index=idx,
            name=str(raw.get("name", "")),
            platform=str(raw.get("platform", "")),
            export_path=str(raw.get("export_path", "")),
            runnable=bool(raw.get("runnable", False)),
            export_filter=str(raw.get("export_filter", "all_resources")),
            include_filter=str(raw.get("include_filter", "")),
            exclude_filter=str(raw.get("exclude_filter", "")),
            raw=dict(raw), options=dict(opts)))
    out.sort(key=lambda p: p.index)
    indices = [p.index for p in out]
    if indices != list(range(len(out))):
        raise PresetError(f"preset indices not contiguous from 0: {indices}")
    return out


def load(project_root: str | Path) -> list[ExportPreset]:
    return from_config(configfile.load(Path(project_root) / "export_presets.cfg"))


def secret_values(preset: ExportPreset) -> list[str]:
    """Keys that look secret and carry a non-empty value (GFX-09)."""
    hits = []
    for key, value in list(preset.raw.items()) + list(preset.options.items()):
        if SECRET_KEY.search(key) and isinstance(value, str) and value.strip():
            hits.append(key)
    return hits


def duplicate_names(presets: list[ExportPreset]) -> list[str]:
    seen: set[str] = set()
    dup = []
    for p in presets:
        if p.name in seen:
            dup.append(p.name)
        seen.add(p.name)
    return dup
