"""Redacted command catalog exposed to planning models."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.commands import CommandCatalog


@dataclass(frozen=True)
class AIToolCard:
    name: str
    description: str
    tags: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    environment_keys: tuple[str, ...]
    max_timeout: float | None
    allow_stdin: bool
    allow_nonzero_success: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "required_capabilities": list(self.required_capabilities),
            "environment_keys": list(self.environment_keys),
            "max_timeout": self.max_timeout,
            "allow_stdin": self.allow_stdin,
            "allow_nonzero_success": self.allow_nonzero_success,
        }


class AIToolCatalog:
    """Model-visible view that intentionally omits executable host paths."""

    def __init__(self, catalog: CommandCatalog) -> None:
        self.catalog = catalog

    def cards(self) -> tuple[AIToolCard, ...]:
        cards = []
        for definition in self.catalog.snapshot():
            cards.append(
                AIToolCard(
                    name=definition.name,
                    description=definition.description,
                    tags=tuple(sorted(definition.spec.tags)),
                    required_capabilities=tuple(
                        sorted(item.value for item in definition.required_capabilities)
                    ),
                    environment_keys=tuple(definition.environment.allowed_keys()),
                    max_timeout=definition.max_timeout,
                    allow_stdin=definition.allow_stdin,
                    allow_nonzero_success=definition.allow_nonzero_success,
                )
            )
        return tuple(cards)

    @property
    def digest(self) -> str:
        raw = json.dumps(
            [item.to_dict() for item in self.cards()],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def model_payload(self) -> tuple[dict[str, object], ...]:
        return tuple(item.to_dict() for item in self.cards())
