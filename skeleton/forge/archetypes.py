"""Blueprint archetypes — named, reusable topology presets.

An archetype stamps components and wires with the standard port layouts
from Forge's stdlib (source / transform / sink / state_store), so new
systems start from a validated skeleton, not an empty canvas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from skeleton.kernel.errors import ForgeError
from skeleton.forge.universal import Blueprint, Forge


class ArchetypeError(ForgeError):
    code = "FRG.ARCHETYPE"


@dataclass(frozen=True)
class Archetype:
    name: str
    build: Callable[[Forge], Blueprint]


class ArchetypeLibrary:
    """Registry of named preset builders."""

    def __init__(self) -> None:
        self._archetypes: Dict[str, Archetype] = {}

    def register(self, archetype: Archetype) -> None:
        self._archetypes[archetype.name] = archetype

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._archetypes))

    def build(self, forge: Forge, name: str) -> Blueprint:
        archetype = self._archetypes.get(name)
        if archetype is None:
            raise ArchetypeError(
                "unknown archetype",
                context={"name": name, "known": list(self._archetypes)},
            )
        return archetype.build(forge)


def default_library() -> ArchetypeLibrary:
    """Ships the 'pipeline' preset (source→transform→sink)."""
    library = ArchetypeLibrary()

    def pipeline(forge: Forge) -> Blueprint:
        bp = forge.new_blueprint("pipeline")
        forge.instantiate(bp, "source", "in")
        forge.instantiate(bp, "transform", "work")
        forge.instantiate(bp, "sink", "out")
        bp.connect(("in", "out"), ("work", "in"))
        bp.connect(("work", "out"), ("out", "in"))
        return bp

    library.register(Archetype(name="pipeline", build=pipeline))
    return library
