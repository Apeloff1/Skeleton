"""Model of a Godot 4 project directory."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import configfile
from .variant import Constructor

IGNORED_DIRS = {".godot", ".import", ".git", "build", "export"}
MAX_PROJECT_SCAN_ENTRIES = 20_000


def _reject_symlink_chain(path: Path) -> None:
    # This is a static source-reference check, not a descriptor-held read.
    # Consumers opening hostile paths must still use openat/O_NOFOLLOW.
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise ValueError("symlinked Godot path or ancestor is not trusted")


def res_to_path(root: Path, res: str) -> Path:
    _reject_symlink_chain(root)
    if type(res) is not str or not res.startswith("res://") or len(res) > 4096:
        raise ValueError("not a bounded res:// path")
    rel = res[len("res://"):]
    parts = rel.split("/")
    if (not rel or rel.startswith("/") or "\\" in rel or "\x00" in rel
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError("unsafe res:// path component")
    if any(char in rel for char in ("%", "?", "#", ":")) or any(
            unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in rel):
        raise ValueError("unsafe res:// URI or control character")
    target = root.joinpath(*parts)
    # Refuse symlinked ancestors as well as the leaf. Never return a
    # plausible res:// reference through a pre-existing alias.
    _reject_symlink_chain(target)
    return target


def path_to_res(root: Path, path: Path) -> str:
    _reject_symlink_chain(root)
    _reject_symlink_chain(path)
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError("Godot resource lies outside the project") from exc
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError("unsafe Godot resource relative path")
    result = "res://" + relative.as_posix()
    res_to_path(root, result)
    return result


@dataclass
class GodotProject:
    root: Path
    config: configfile.ConfigFile

    @classmethod
    def load(cls, root: str | Path) -> "GodotProject":
        r = Path(root)
        _reject_symlink_chain(r)
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
        if type(v) is str and 1 <= len(v) <= 4 and v.isascii() and v.isdecimal():
            v = int(v)
        if type(v) is not int or not 1 <= v <= 1000:
            raise ValueError("invalid bounded Godot physics tick rate")
        return v

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
        _reject_symlink_chain(self.root)
        out = []
        visited = 0
        for p in self.root.rglob("*"):
            visited += 1
            if visited > MAX_PROJECT_SCAN_ENTRIES:
                raise ValueError("project scan exceeds entry bound")
            if p.is_symlink():
                raise ValueError("symlinked Godot inventory entry is not trusted")
            if not p.is_file() or p.suffix not in suffixes:
                continue
            if any(part in IGNORED_DIRS for part in p.relative_to(self.root).parts):
                continue
            out.append(p)
        return sorted(out)

    def scripts(self) -> list[Path]:
        return self.iter_files((".gd",))

    def scenes(self) -> list[Path]:
        return self.iter_files((".tscn", ".scn"))

    def resources(self) -> list[Path]:
        return self.iter_files((".tres", ".res"))
