"""Deterministic hermetic fixture registry for VOL-196."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import sha256_json
from .operations_experience import Fixture


@dataclass(frozen=True, slots=True)
class FixtureManifest:
    fixture_ids: tuple[str, ...]
    fixture_digests: tuple[str, ...]
    manifest_digest: str


class FixtureRegistry:
    def __init__(self, fixtures: Iterable[Fixture]) -> None:
        items = tuple(fixtures)
        if not items:
            raise ValueError("fixture registry cannot be empty")
        ids = [item.fixture_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("fixture ids must be unique")
        unsafe = [item.fixture_id for item in items if not item.hermetic or item.external_side_effects]
        if unsafe:
            raise ValueError("registered fixtures must be hermetic and side-effect free: " + ",".join(sorted(unsafe)))
        self._fixtures = {item.fixture_id: item for item in items}

    def require(self, fixture_id: str, *, expected_digest: str) -> Fixture:
        fixture = self._fixtures.get(fixture_id)
        if fixture is None:
            raise KeyError("unknown fixture")
        if fixture.digest != expected_digest:
            raise ValueError("fixture digest mismatch")
        return fixture

    def manifest(self) -> FixtureManifest:
        ordered = tuple(self._fixtures[key] for key in sorted(self._fixtures))
        payload = [{"fixture_id": item.fixture_id, "digest": item.digest} for item in ordered]
        return FixtureManifest(
            fixture_ids=tuple(item.fixture_id for item in ordered),
            fixture_digests=tuple(item.digest for item in ordered),
            manifest_digest=sha256_json(payload),
        )
