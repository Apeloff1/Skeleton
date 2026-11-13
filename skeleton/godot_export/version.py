"""Godot version string parsing (``4.7.2.stable.official.abc123``)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?:\.(?P<status>[a-z]+\d*))?(?:\.(?P<build>[A-Za-z0-9_]+))?(?:\.(?P<hash>[0-9a-f]+))?")
_STATUS_RANK = {"dev": 0, "alpha": 1, "beta": 2, "rc": 3, "stable": 4}


@dataclass(frozen=True, order=False)
class GodotVersion:
    major: int
    minor: int
    patch: int = 0
    status: str = "stable"
    build: str = ""
    commit: str = ""

    def key(self) -> tuple[int, int, int, int, int]:
        m = re.match(r"([a-z]+)(\d*)", self.status)
        name, num = (m.group(1), int(m.group(2) or 0)) if m else ("stable", 0)
        return (self.major, self.minor, self.patch, _STATUS_RANK.get(name, -1), num)

    def __lt__(self, other: "GodotVersion") -> bool:
        return self.key() < other.key()

    def __le__(self, other: "GodotVersion") -> bool:
        return self.key() <= other.key()

    def short(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def matches_pin(self, pin: str) -> bool:
        p = parse(pin)
        return (self.major, self.minor, self.patch, self.status) == (p.major, p.minor, p.patch, p.status)


def parse(text: str) -> GodotVersion:
    m = _VERSION.match(text.strip())
    if not m:
        raise ValueError(f"not a Godot version: {text!r}")
    return GodotVersion(int(m.group("major")), int(m.group("minor")), int(m.group("patch") or 0),
                        m.group("status") or "stable", m.group("build") or "", m.group("hash") or "")


def feature_version(features: list[str]) -> GodotVersion | None:
    for f in features:
        try:
            return parse(f)
        except ValueError:
            continue
    return None
