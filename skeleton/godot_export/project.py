"""Model of a Godot 4 project directory."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import configfile
from .variant import Constructor

IGNORED_DIRS = {".godot", ".import", ".git", "build", "export"}


def res_to_path(root: Path, res: str) -> Path:
    if not res.startswith("res://"):
        raise ValueError(f"not a res:// path: {res}")
    rel = res[len("res://"):]
    if ".." in Path(rel).parts:
        raise ValueError(f"res:// path escapes project: {res}")
    return root / rel


def path_to_res(root: Path, path: Path) -> str:
    return "res://" + path.resolve().relative_to(root.resolve()).as_posix()


@dataclass
class GodotProject:
    root: Path
    config: configfile.ConfigFile

    @classmethod
    def load(cls, root: str | Path) -> "GodotProject":
        r = Path(root)
        return cls(r, configfile.load(r / "project.godot"))

    @property
    def config_version(self) -> int | None:
        v = self.config.header.get("config_version")
        return v if isinstance(v, int) else None

    @property
    def name(self) -> str:
        return str(self.config.get("application", "config/name", ""))

    @property
    def main_scene(self) -> str | None:
        v = self.config.get("application", "run/main_scene")
        return v if isinstance(v, str) and v else None

    @property
    def features(self) -> list[str]:
        v = self.config.get("application", "config/features")
        if isinstance(v, Constructor):
            return [str(a) for a in v.args]
        if isinstance(v, list):
            return [str(a) for a in v]
        return []

    @property
    def engine_version(self) -> str | None:
        for f in self.features:
            if f[:1].isdigit():
                return f
        return None

    @property
    def physics_ticks(self) -> int:
        v = self.config.get("physics", "common/physics_ticks_per_second", 60)
        return int(v)

    @property
    def autoloads(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in self.config.sections.get("autoload", {}).items():
            if isinstance(v, str):
                out[k] = v.lstrip("*")
        return out

    def setting(self, section: str, key: str, default: Any = None) -> Any:
        return self.config.get(section, key, default)

    def exists(self, res: str) -> bool:
        try:
            return res_to_path(self.root, res).exists()
        except ValueError:
            return False

    def iter_files(self, suffixes: tuple[str, ...]) -> list[Path]:
        out = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or p.suffix not in suffixes:
                continue
            if any(part in IGNORED_DIRS for part in p.relative_to(self.root).parts):
                continue
            out.append(p)
        return out

    def scripts(self) -> list[Path]:
        return self.iter_files((".gd",))

    def scenes(self) -> list[Path]:
        return self.iter_files((".tscn", ".scn"))

    def resources(self) -> list[Path]:
        return self.iter_files((".tres", ".res"))
