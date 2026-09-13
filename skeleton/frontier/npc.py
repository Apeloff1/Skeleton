"""Provider-neutral NPC generation contracts for the frontier runtime.

This module intentionally contains deterministic scaffolding rather than a
model-specific implementation. Domain adapters can plug an LLM behind the
contract without coupling the kernel to a vendor or web framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class NPCSpec:
    """Validated, serializable NPC specification."""

    name: str
    archetype: str
    description: str
    traits: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    stats: Mapping[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "archetype": self.archetype,
            "description": self.description,
            "traits": list(self.traits),
            "tags": list(self.tags),
            "stats": dict(self.stats),
        }


class NPCGenerator:
    """Deterministic baseline generator used for adapter and integration tests."""

    def generate(
        self,
        description: str,
        *,
        archetype: str = "citizen",
        name: str = "Generated NPC",
        traits: Sequence[str] = (),
    ) -> NPCSpec:
        if not description.strip():
            raise ValueError("description must not be empty")
        if not archetype.strip():
            raise ValueError("archetype must not be empty")
        return NPCSpec(
            name=name.strip() or "Generated NPC",
            archetype=archetype.strip().lower(),
            description=description.strip(),
            traits=tuple(t.strip().lower() for t in traits if t.strip()),
        )
