"""Godot ConfigFile reader/writer (``project.godot``, ``export_presets.cfg``).

The format is INI-like: ``[section]`` headers, ``key=value`` pairs where value
is a Variant literal that may span multiple lines, and ``;`` comments. Keys may
contain ``/`` (``application/config/name``). Order is preserved so files can be
round-tripped with extend-only edits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import variant

_SECTION = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KEY = re.compile(r"^(?P<key>[^=\s][^=]*?)\s*=\s*(?P<value>.*)$")


class ConfigParseError(ValueError):
    def __init__(self, message: str, line: int, path: str = "") -> None:
        super().__init__(f"{path or '<config>'}:{line}: {message}")
        self.line = line
        self.path = path


@dataclass
class ConfigFile:
    """Ordered mapping of sections to ordered key/value pairs."""

    header: dict[str, Any] = field(default_factory=dict)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    path: str = ""

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.sections.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        self.sections.setdefault(section, {})[key] = value

    def has_section(self, section: str) -> bool:
        return section in self.sections

    def keys(self, section: str) -> list[str]:
        return list(self.sections.get(section, {}))

    def items(self) -> Iterator[tuple[str, str, Any]]:
        for sec, values in self.sections.items():
            for key, value in values.items():
                yield sec, key, value

    def section_names(self, prefix: str = "") -> list[str]:
        return [s for s in self.sections if s.startswith(prefix)]

    def dumps(self) -> str:
        lines: list[str] = []
        for key, value in self.header.items():
            lines.append(f"{key}={variant.dump(value)}")
        if self.header:
            lines.append("")
        for sec, values in self.sections.items():
            lines.append(f"[{sec}]")
            lines.append("")
            for key, value in values.items():
                lines.append(f"{key}={variant.dump(value)}")
            lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"


def loads(text: str, path: str = "") -> ConfigFile:
    cfg = ConfigFile(path=path)
    current: dict[str, Any] | None = None
    pending_key: str | None = None
    pending_line = 0
    buffer: list[str] = []

    def commit() -> None:
        nonlocal pending_key, buffer
        if pending_key is None:
            return
        raw = "\n".join(buffer).strip()
        try:
            value = variant.parse(raw)
        except variant.VariantParseError as exc:
            raise ConfigParseError(str(exc), pending_line, path) from exc
        target = current if current is not None else cfg.header
        target[pending_key] = value
        pending_key = None
        buffer = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if pending_key is not None:
            buffer.append(raw_line)
            if variant.is_complete("\n".join(buffer)):
                commit()
            continue
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        m = _SECTION.match(line)
        if m:
            name = m.group("name").strip()
            if name in cfg.sections:
                raise ConfigParseError(f"duplicate section [{name}]", lineno, path)
            current = cfg.sections.setdefault(name, {})
            continue
        m = _KEY.match(line)
        if not m:
            raise ConfigParseError(f"unparseable line {line!r}", lineno, path)
        pending_key = m.group("key").strip()
        pending_line = lineno
        buffer = [m.group("value")]
        if variant.is_complete(m.group("value")):
            commit()
    if pending_key is not None:
        raise ConfigParseError(f"unterminated value for {pending_key!r}", pending_line, path)
    return cfg


def load(path: str | Path) -> ConfigFile:
    p = Path(path)
    return loads(p.read_text(encoding="utf-8"), str(p))
