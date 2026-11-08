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
import json
import math
from dataclasses import dataclass, field
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
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_PAYLOAD_NODES = 20_000
MAX_PAYLOAD_DEPTH = 32
MAX_COLLECTION_ITEMS = 4096

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


def _payload_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Make a bounded JSON-only source snapshot before copying or hashing.

    Reject cyclic, exotic, nonfinite and oversized values rather than letting
    deepcopy or json.dumps allocate an unbounded, mutable migration envelope.
    """
    if not isinstance(payload, Mapping) or len(payload) > MAX_COLLECTION_ITEMS:
        raise GameplayMigrationError("gameplay payload top-level budget exceeded")
    original = dict(payload)
    pending = [(original, 0)]
    remaining = MAX_PAYLOAD_NODES
    while pending:
        value, depth = pending.pop()
        remaining -= 1
        if remaining < 0 or depth > MAX_PAYLOAD_DEPTH:
            raise GameplayMigrationError("gameplay payload structural budget exceeded")
        if type(value) is dict:
            if len(value) > MAX_COLLECTION_ITEMS:
                raise GameplayMigrationError("gameplay payload mapping budget exceeded")
            for key, child in value.items():
                if type(key) is not str or len(key) > 256:
                    raise GameplayMigrationError("gameplay payload keys must be bounded text")
                pending.append((child, depth + 1))
        elif type(value) in (list, tuple):
            if len(value) > MAX_COLLECTION_ITEMS:
                raise GameplayMigrationError("gameplay payload sequence budget exceeded")
            pending.extend((child, depth + 1) for child in value)
        elif type(value) is str:
            if len(value) > MAX_PAYLOAD_BYTES:
                raise GameplayMigrationError("gameplay payload text budget exceeded")
        elif value is None or type(value) is bool:
            pass
        elif type(value) is int:
            if not -(2 ** 63) <= value < 2 ** 63:
                raise GameplayMigrationError("gameplay payload integer budget exceeded")
        elif type(value) is float and math.isfinite(value):
            pass
        else:
            raise GameplayMigrationError("gameplay payload contains non-JSON value")
    try:
        encoded = json.dumps(original, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise GameplayMigrationError("gameplay payload encoded byte budget exceeded")
        return json.loads(encoded)
    except (ValueError, TypeError, UnicodeError, OverflowError,
            RecursionError) as exc:
        raise GameplayMigrationError("invalid bounded gameplay payload") from exc


@dataclass(frozen=True)
class GameplayStateEnvelope:
    world_id: str
    schema_version: int
    tick: int
    payload: Mapping[str, Any]
    canon_digest: str
    parent_save_digest: str | None = None
    _admitted_digest: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        req_id(self.world_id, "world_id")
        _version(self.schema_version, "schema_version")
        if not _int(self.tick) or self.tick < 0:
            raise GameplayMigrationError("invalid tick")
        if not isinstance(self.payload, Mapping):
            raise GameplayMigrationError("payload must be a mapping")
        req_digest(self.canon_digest, "canon_digest")
        if self.parent_save_digest is not None:
            req_digest(self.parent_save_digest, "parent_save_digest")
        snapshot = _payload_snapshot(self.payload)
        object.__setattr__(self, "payload", snapshot)
        object.__setattr__(self, "_admitted_digest", dig(snapshot))

    @property
    def state_digest(self) -> str:
        # Recheck bounds before hashing; callers can still hold a reference
        # to the detached dict and must not expand it after admission.
        actual = dig(_payload_snapshot(self.payload))
        if actual != self._admitted_digest:
            raise GameplayMigrationError("gameplay payload mutated after admission")
        return actual

    def metadata(self) -> SaveableGameplayState:
        return SaveableGameplayState(self.world_id, self.schema_version, self.tick,
                                     self.state_digest, self.canon_digest, self.parent_save_digest)

    @property
    def digest(self) -> str:
        return self.metadata().digest

    def to_section(self) -> Dict[str, Any]:
        """Plain dict for a GF-B (#4246) save section; round-trips via ``from_section``."""
        admitted_digest = self.state_digest
        return {"schema": ENVELOPE_SCHEMA, "world_id": self.world_id,
                "schema_version": self.schema_version, "tick": self.tick,
                "payload": copy.deepcopy(dict(self.payload)), "canon_digest": self.canon_digest,
                "parent_save_digest": self.parent_save_digest, "state_digest": admitted_digest}

    @classmethod
    def from_section(cls, section: Mapping[str, Any]) -> "GameplayStateEnvelope":
        if not isinstance(section, Mapping):
            raise GameplayMigrationError("gameplay save section must be a mapping")
        required = {"schema", "world_id", "schema_version", "tick", "payload",
                    "canon_digest", "state_digest"}
        allowed = required | {"parent_save_digest"}
        if not required.issubset(section) or set(section) - allowed:
            raise GameplayMigrationError("gameplay save section fields invalid")
        if section["schema"] != ENVELOPE_SCHEMA:
            raise GameplayMigrationError("unknown gameplay save schema")
        env = cls(section["world_id"], section["schema_version"], section["tick"],
                  section["payload"], section["canon_digest"], section.get("parent_save_digest"))
        if section["state_digest"] != env.state_digest:
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
            raise GameplayMigrationError("migration step must be callable")
        self._steps[from_version] = fn

    def missing_steps(self, oldest: int = 1) -> tuple[int, ...]:
        if not _int(oldest) or not 1 <= oldest <= self.current_version:
            raise GameplayMigrationError("invalid oldest schema version")
        return tuple(v for v in range(oldest, self.current_version) if v not in self._steps)

    def _step(self, v: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        fn = self._steps.get(v)
        if fn is None:
            raise GameplayMigrationError(f"missing migration step {v}->{v + 1}")
        a = fn(copy.deepcopy(payload))
        b = fn(copy.deepcopy(payload))
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise GameplayMigrationError(f"non-deterministic migration {v}->{v + 1}")
        a_snapshot = _payload_snapshot(a)
        b_snapshot = _payload_snapshot(b)
        if dig(a_snapshot) != dig(b_snapshot):
            raise GameplayMigrationError(f"non-deterministic migration {v}->{v + 1}")
        return a_snapshot

    def migrate(self, env: GameplayStateEnvelope) -> tuple[GameplayStateEnvelope, MigrationReport]:
        if env.schema_version > self.current_version:
            raise GameplayMigrationError("save is newer than this build")
        source_digest = env.state_digest
        payload = copy.deepcopy(dict(env.payload))
        steps = []
        for v in range(env.schema_version, self.current_version):
            payload = self._step(v, payload)
            steps.append(v)
        out = GameplayStateEnvelope(env.world_id, self.current_version, env.tick, payload,
                                    env.canon_digest, env.parent_save_digest)
        return out, MigrationReport(env.schema_version, self.current_version, tuple(steps),
                                    source_digest, out.state_digest)

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
