"""Hermetic, versioned fixture contracts for deterministic tests.

VOL-196 requires fixtures to make ownership, provenance and side-effect
authority explicit.  This module intentionally uses only stdlib primitives so
the registry itself cannot introduce network, wall-clock, or random leakage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable, Dict, Mapping, Tuple


class FixtureContractError(ValueError):
    """Raised when a fixture violates the hermetic fixture contract."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, order=True)
class FixtureVersion:
    major: int = 1
    minor: int = 0
    patch: int = 0

    def __post_init__(self) -> None:
        if min(self.major, self.minor, self.patch) < 0:
            raise FixtureContractError("fixture version components must be non-negative")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class Fixture:
    """A deterministic fixture factory with explicit provenance and authority."""

    name: str
    build: Callable[[], Any]
    owner: str = "skeleton/testing"
    scope: str = "unit"
    version: FixtureVersion = field(default_factory=FixtureVersion)
    provenance: str = "generated"
    allows_network: bool = False
    allows_wall_clock: bool = False
    allows_randomness: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise FixtureContractError("fixture name is required")
        if not self.owner.strip():
            raise FixtureContractError("fixture owner is required")
        if not self.scope.strip():
            raise FixtureContractError("fixture scope is required")
        if not self.provenance.strip():
            raise FixtureContractError("fixture provenance is required")

    @property
    def hermetic(self) -> bool:
        return not (self.allows_network or self.allows_wall_clock or self.allows_randomness)

    @property
    def identity(self) -> str:
        payload = {
            "name": self.name,
            "owner": self.owner,
            "scope": self.scope,
            "version": str(self.version),
            "provenance": self.provenance,
            "authority": {
                "network": self.allows_network,
                "wall_clock": self.allows_wall_clock,
                "randomness": self.allows_randomness,
            },
        }
        return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FixtureReceipt:
    name: str
    identity: str
    version: str
    owner: str
    scope: str
    provenance: str
    hermetic: bool


class FixtureRegistry:
    """Named fixture factories with deterministic inventory and fail-closed policy."""

    def __init__(self, *, require_hermetic: bool = True) -> None:
        self._fixtures: Dict[str, Fixture] = {}
        self._require_hermetic = require_hermetic

    def register(self, fixture: Fixture) -> Fixture:
        if fixture.name in self._fixtures:
            raise FixtureContractError(f"duplicate fixture: {fixture.name}")
        if self._require_hermetic and not fixture.hermetic:
            raise FixtureContractError(
                f"fixture {fixture.name!r} requests non-hermetic authority"
            )
        self._fixtures[fixture.name] = fixture
        return fixture

    def build(self, name: str) -> Any:
        fixture = self._fixtures.get(name)
        if fixture is None:
            raise KeyError(name)
        return fixture.build()

    def receipt(self, name: str) -> FixtureReceipt:
        fixture = self._fixtures.get(name)
        if fixture is None:
            raise KeyError(name)
        return FixtureReceipt(
            name=fixture.name,
            identity=fixture.identity,
            version=str(fixture.version),
            owner=fixture.owner,
            scope=fixture.scope,
            provenance=fixture.provenance,
            hermetic=fixture.hermetic,
        )

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._fixtures))

    def inventory(self) -> Tuple[FixtureReceipt, ...]:
        return tuple(self.receipt(name) for name in self.names())

    def manifest(self) -> Mapping[str, object]:
        receipts = [
            {
                "name": r.name,
                "identity": r.identity,
                "version": r.version,
                "owner": r.owner,
                "scope": r.scope,
                "provenance": r.provenance,
                "hermetic": r.hermetic,
            }
            for r in self.inventory()
        ]
        payload = {"schema": "skeleton.fixture-registry.v1", "fixtures": receipts}
        return {**payload, "digest": hashlib.sha256(_canonical(payload).encode()).hexdigest()}
