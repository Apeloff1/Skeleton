"""Test fixtures — deterministic factories for the scaffold helpers.

scaffold.py runs generic cases; fixtures provide named builders
(default_document, default_chunker, default_skill_model) for the
softened API the TestScaffold contract expects given() to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple


@dataclass(frozen=True)
class Fixture:
    name: str
    build: Callable[[], Any]


class FixtureRegistry:
    """Named fixture factories; register once per test-suite."""

    def __init__(self) -> None:
        self._fixtures: Dict[str, Fixture] = {}

    def register(self, fixture: Fixture) -> Fixture:
        self._fixtures[fixture.name] = fixture
        return fixture

    def build(self, name: str) -> Any:
        fixture = self._fixtures.get(name)
        if fixture is None:
            raise KeyError(name)
        return fixture.build()

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._fixtures))
