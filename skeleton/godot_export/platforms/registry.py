"""Platform name -> spec."""
from __future__ import annotations

from . import android, ios, linux, macos, web, windows
from .base import PlatformSpec

REGISTRY: dict[str, PlatformSpec] = {
    s.name: s for s in (linux.SPEC, windows.SPEC, macos.SPEC, web.SPEC, android.SPEC, ios.SPEC)
}
ALIASES = {"Linux/X11": "Linux", "Windows": "Windows Desktop", "Mac OSX": "macOS", "HTML5": "Web"}


def canonical(name: str) -> str:
    return ALIASES.get(name, name)


def known(name: str) -> bool:
    return canonical(name) in REGISTRY


def get(name: str) -> PlatformSpec:
    try:
        return REGISTRY[canonical(name)]
    except KeyError as exc:
        raise KeyError(f"unknown export platform {name!r}") from exc
