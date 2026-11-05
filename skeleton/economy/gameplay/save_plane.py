"""B025 adapter: the economy save as one :class:`GameSavePlane` section.

The economy save (:mod:`skeleton.economy.gameplay.save`, formats v1-v3) is
stored inside a game save as a single section keyed by section name plus
format version, e.g. ``"economy@v3"``. Versioning of the economy payload is
owned by ``save.py``: on read this adapter only locates the section, checks
that its key and payload agree on the version, and delegates to
:func:`save.migrate` / :func:`save.load`. The plane's own ``schema_version``
(whole-save layout) is independent of the economy format version.

Gameplay runtime state lives in its own section (``GameplayStateEnvelope``)
and is deliberately not touched here; other sections pass through unchanged.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Optional

from skeleton.economy.gameplay import save as economy_save
from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.save import SaveError
from skeleton.kernel.checkpoint import Checkpoint
from skeleton.kernel.game_save_plane import GameSavePlane

SECTION_NAME = "economy"
_KEY_RE = re.compile(r"^(?P<name>[a-z_]+)@v(?P<version>\d+)$")


def section_key(
    version: int = economy_save.SAVE_VERSION, name: str = SECTION_NAME
) -> str:
    return f"{name}@v{version}"


def economy_section(
    econ: GameplayEconomy, name: str = SECTION_NAME
) -> dict[str, dict[str, Any]]:
    """Return ``{key: payload}`` for merging into a plane ``sections`` map."""
    data = economy_save.save(econ)
    return {section_key(data["version"], name): data}


def find_section(
    sections: Mapping[str, Any], name: str = SECTION_NAME
) -> tuple[int, Mapping[str, Any]]:
    found = []
    for key, payload in sections.items():
        m = _KEY_RE.match(key)
        if m and m.group("name") == name:
            found.append((int(m.group("version")), payload))
    if not found:
        raise SaveError(f"save has no {name!r} section")
    if len(found) > 1:
        raise SaveError(f"save has more than one {name!r} section")
    version, payload = found[0]
    if not isinstance(payload, Mapping) or payload.get("version") != version:
        raise SaveError(f"{name!r} section key and payload disagree on version")
    if version < 1 or version > economy_save.SAVE_VERSION:
        raise SaveError(f"unknown {name!r} section version v{version}")
    return version, payload


def save_to_plane(
    plane: GameSavePlane,
    slot: str,
    sequence: int,
    econ: GameplayEconomy,
    *,
    other_sections: Optional[Mapping[str, Mapping[str, Any]]] = None,
    name: str = SECTION_NAME,
) -> Checkpoint:
    sections: dict[str, Mapping[str, Any]] = dict(other_sections or {})
    if any((m := _KEY_RE.match(k)) and m.group("name") == name for k in sections):
        raise SaveError(f"other_sections already holds a {name!r} section")
    sections.update(economy_section(econ, name))
    return plane.save(slot, sequence, sections)


def load_from_plane(
    plane: GameSavePlane,
    slot: str,
    factory: Callable[[], GameplayEconomy],
    *,
    sequence: Optional[int] = None,
    name: str = SECTION_NAME,
) -> GameplayEconomy:
    sections, _ = plane.restore(slot, sequence=sequence)
    _, payload = find_section(sections, name)
    return economy_save.load(payload, factory)


__all__ = [
    "SECTION_NAME",
    "economy_section",
    "find_section",
    "load_from_plane",
    "save_to_plane",
    "section_key",
]
