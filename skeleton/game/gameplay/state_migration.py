"""B025 gameplay save/state schema and migration.

Versioned gameplay-state envelopes with a chained, deterministic migration
registry and backward-compatibility checks. Extends the FLGB-13
:class:`~skeleton.game.gameplay.flgb_gameplay_runtime.SaveableGameplayState`
metadata contract (it is produced, never replaced) and reuses its canonical
``dig`` digest.

Storage is deliberately out of scope: durable checkpoints, rollback, backups
and chunk receipts belong to the GF-B save plane (PR #4246,
``skeleton.kernel.game_save_plane``). This module owns the *gameplay schema*
layer that plugs into it: :meth:`GameplayMigrations.as_section_migrations`
yields ``{from_version: fn(dict) -> dict}`` callables with the same shape as
``GameSavePlane.register_migration``, and :meth:`GameplayStateEnvelope.to_section`
emits a plain section dict for a GF-B save.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    GameplayContractError,
    SaveableGameplayState,
    _int,
    dig,
    req_digest,
    req_id,
)

ENVELOPE_SCHEMA = "skeleton.game.gameplay_state.v1"
MAX_SCHEMA_VERSION = 10_000
MAX_PAYLOAD_NODES = 10_000
MAX_PAYLOAD_DEPTH = 32
MAX_MIGRATION_STEPS = 128
MAX_GAMEPLAY_TICK = 2**63 - 1
SECTION_KEYS = frozenset({
    "schema", "world_id", "schema_version", "tick", "payload",
    "canon_digest", "parent_save_digest", "state_digest",
})

Migration = Callable[[Dict[str, Any]], Dict[str, Any]]

__all__ = [
    "ENVELOPE_SCHEMA", "GameplayMigrationError", "GameplayMigrations",
    "GameplayStateEnvelope", "MigrationReport",
]


class GameplayMigrationError(GameplayContractError):
    """Gameplay save could not be loaded or migrated safely."""


def _version(v: object, name: str) -> int:
    if not _int(v) or not 1 <= v <= MAX_SCHEMA_VERSION:  # type: ignore[operator]
        raise GameplayMigrationError(f"invalid {name}")
    return v  # type: ignore[return-value]


def _bounded_payload(payload: Mapping[str, Any]) -> None:
    """Reject cyclic or oversized save payloads before deepcopy/JSON hashing."""
    active: set[int] = set()
    visited = 0

    def walk(value: Any, depth: int) -> None:
        nonlocal visited
        visited += 1
        if visited > MAX_PAYLOAD_NODES or depth > MAX_PAYLOAD_DEPTH:
            raise GameplayMigrationError("gameplay payload traversal budget exceeded")
        if isinstance(value, (Mapping, list, tuple)):
            identity = id(value)
            if identity in active:
                raise GameplayMigrationError("cyclic gameplay payload")
            active.add(identity)
            try:
                if len(value) > MAX_PAYLOAD_NODES:
                    raise GameplayMigrationError("gameplay payload collection exceeds bound")
                if isinstance(value, Mapping):
                    for key, child in value.items():
                        if type(key) is not str or len(key) > 256:
                            raise GameplayMigrationError("invalid gameplay payload key")
                        walk(child, depth + 1)
                else:
                    for child in value:
                        walk(child, depth + 1)
            finally:
                active.remove(identity)
        elif type(value) is str:
            if len(value) > 4096:
                raise GameplayMigrationError("gameplay payload text exceeds bound")
        elif type(value) is int:
            if value.bit_length() > 4096:
                raise GameplayMigrationError("gameplay payload integer exceeds bound")
        elif type(value) is float:
            if not math.isfinite(value):
                raise GameplayMigrationError("nonfinite gameplay payload value")
        elif type(value) not in (bool, type(None)):
            raise GameplayMigrationError("noncanonical gameplay payload value")

    walk(payload, 0)


@dataclass(frozen=True)
class GameplayStateEnvelope:
    world_id: str
    schema_version: int
    tick: int
    payload: Mapping[str, Any]
    canon_digest: str
    parent_save_digest: str | None = None

    def __post_init__(self) -> None:
        req_id(self.world_id, "world_id")
        _version(self.schema_version, "schema_version")
        if not _int(self.tick) or not 0 <= self.tick <= MAX_GAMEPLAY_TICK:
            raise GameplayMigrationError("invalid bounded tick")
        if not isinstance(self.payload, Mapping):
            raise GameplayMigrationError("payload must be a mapping")
        req_digest(self.canon_digest, "canon_digest")
        if self.parent_save_digest is not None:
            req_digest(self.parent_save_digest, "parent_save_digest")
        _bounded_payload(self.payload)
        object.__setattr__(self, "payload", copy.deepcopy(dict(self.payload)))
        dig(self.payload)  # rejects non-canonical (NaN, non-JSON) payloads

    @property
    def state_digest(self) -> str:
        return dig(self.payload)

    def metadata(self) -> SaveableGameplayState:
        return SaveableGameplayState(self.world_id, self.schema_version, self.tick,
                                     self.state_digest, self.canon_digest, self.parent_save_digest)

    @property
    def digest(self) -> str:
        return self.metadata().digest

    def to_section(self) -> Dict[str, Any]:
        """Plain dict for a GF-B (#4246) save section; round-trips via ``from_section``."""
        return {"schema": ENVELOPE_SCHEMA, "world_id": self.world_id,
                "schema_version": self.schema_version, "tick": self.tick,
                "payload": copy.deepcopy(dict(self.payload)), "canon_digest": self.canon_digest,
                "parent_save_digest": self.parent_save_digest, "state_digest": self.state_digest}

    @classmethod
    def from_section(cls, section: Mapping[str, Any]) -> "GameplayStateEnvelope":
        # Untrusted serialized saves must be plain JSON dictionaries. Do not
        # execute custom Mapping iteration/lookup hooks before shape checks.
        if type(section) is not dict:
            raise GameplayMigrationError("gameplay save schema section must be a plain dict")
        if section.get("schema") != ENVELOPE_SCHEMA:
            raise GameplayMigrationError("unknown gameplay save schema")
        if len(section) != len(SECTION_KEYS):
            missing = SECTION_KEYS - section.keys()
            if missing:
                raise GameplayMigrationError("missing gameplay save field")
            raise GameplayMigrationError("unknown gameplay save field")
        if set(section) != SECTION_KEYS:
            raise GameplayMigrationError("unknown gameplay save field")
        if type(section["payload"]) is not dict:
            raise GameplayMigrationError("gameplay save payload must be a plain dict")
        try:
            env = cls(section["world_id"], section["schema_version"], section["tick"],
                      section["payload"], section["canon_digest"], section.get("parent_save_digest"))
        except KeyError:
            raise GameplayMigrationError("missing gameplay save field") from None
        if section.get("state_digest") != env.state_digest:
            raise GameplayMigrationError("gameplay save digest mismatch")
        return env


@dataclass(frozen=True)
class MigrationReport:
    from_version: int
    to_version: int
    steps: tuple[int, ...]
    source_digest: str
    result_digest: str


class GameplayMigrations:
    """Chained ``v -> v+1`` payload migrations, deterministic and forward-only."""

    def __init__(self, current_version: int) -> None:
        self.current_version = _version(current_version, "current_version")
        self._steps: Dict[int, Migration] = {}

    def register(self, from_version: int, fn: Migration) -> None:
        _version(from_version, "from_version")
        if from_version >= self.current_version:
            raise GameplayMigrationError("migration beyond current version")
        if from_version in self._steps:
            raise GameplayMigrationError("migration already registered")
        if not callable(fn):
            raise GameplayMigrationError("migration callback must be callable")
        self._steps[from_version] = fn

    def missing_steps(self, oldest: int = 1) -> tuple[int, ...]:
        oldest = _version(oldest, "oldest")
        if oldest > self.current_version:
            raise GameplayMigrationError("oldest version exceeds current version")
        return tuple(v for v in range(oldest, self.current_version) if v not in self._steps)

    def _step(self, v: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        fn = self._steps.get(v)
        if fn is None:
            raise GameplayMigrationError(f"missing migration step {v}->{v + 1}")
        a = fn(copy.deepcopy(payload))
        if not isinstance(a, dict):
            raise GameplayMigrationError(f"non-deterministic migration {v}->{v + 1}")
        # Reject a malformed first result BEFORE invoking the callback again.
        # No second side effect is permitted after an already failed boundary.
        _bounded_payload(a)
        b = fn(copy.deepcopy(payload))
        if not isinstance(b, dict):
            raise GameplayMigrationError(f"non-deterministic migration {v}->{v + 1}")
        _bounded_payload(b)
        if dig(a) != dig(b):
            raise GameplayMigrationError(f"non-deterministic migration {v}->{v + 1}")
        return a

    def migrate(self, env: GameplayStateEnvelope) -> tuple[GameplayStateEnvelope, MigrationReport]:
        if env.schema_version > self.current_version:
            raise GameplayMigrationError("save is newer than this build")
        if self.current_version - env.schema_version > MAX_MIGRATION_STEPS:
            raise GameplayMigrationError("migration chain exceeds step bound")
        payload = copy.deepcopy(dict(env.payload))
        steps = []
        for v in range(env.schema_version, self.current_version):
            payload = self._step(v, payload)
            steps.append(v)
        out = GameplayStateEnvelope(env.world_id, self.current_version, env.tick, payload,
                                    env.canon_digest, env.parent_save_digest)
        return out, MigrationReport(env.schema_version, self.current_version, tuple(steps),
                                    env.state_digest, out.state_digest)

    def load_section(self, section: Mapping[str, Any]) -> tuple[GameplayStateEnvelope, MigrationReport]:
        return self.migrate(GameplayStateEnvelope.from_section(section))

    def as_section_migrations(self) -> Dict[int, Migration]:
        """Section-level steps shaped for ``GameSavePlane.register_migration`` (#4246)."""
        def make(v: int) -> Migration:
            def fn(section: Dict[str, Any]) -> Dict[str, Any]:
                env = GameplayStateEnvelope.from_section(section)
                if env.schema_version != v:
                    raise GameplayMigrationError("section version mismatch")
                nxt = GameplayStateEnvelope(env.world_id, v + 1, env.tick, self._step(v, dict(env.payload)),
                                            env.canon_digest, env.parent_save_digest)
                return nxt.to_section()
            return fn
        return {v: make(v) for v in sorted(self._steps)}
