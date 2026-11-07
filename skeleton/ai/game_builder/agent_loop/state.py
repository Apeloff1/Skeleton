"""Authoritative game state: the only mutation path is a guarded, validated,
versioned ``apply``. Readers only ever get immutable snapshots."""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping


class StateMutationError(ValueError):
    """Raised when a mutation fails validation; state is left untouched."""


class StaleVersionError(StateMutationError):
    """Raised when a mutation was computed against an older version."""


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return value


def _digest(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class GameSnapshot:
    version: int
    data: Mapping[str, Any]
    digest: str

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass(frozen=True)
class Mutation:
    """A set of top-level key updates proposed against ``base_version``."""
    base_version: int
    updates: Mapping[str, Any]
    actor: str = "agent"
    reason: str = ""


Validator = Callable[[Mapping[str, Any], Mutation], None]


@dataclass
class AuthoritativeGameState:
    initial: Mapping[str, Any] = field(default_factory=dict)
    validators: list[Validator] = field(default_factory=list)
    protected_keys: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        self._data: dict[str, Any] = copy.deepcopy(dict(self.initial))
        self._version = 0
        self._lock = threading.Lock()
        self._history: list[tuple[int, str, str, str]] = [(0, "init", "", _digest(self._data))]

    @property
    def version(self) -> int:
        return self._version

    @property
    def history(self) -> tuple[tuple[int, str, str, str], ...]:
        return tuple(self._history)

    def snapshot(self) -> GameSnapshot:
        with self._lock:
            data = copy.deepcopy(self._data)
            return GameSnapshot(self._version, _freeze(data), _digest(data))

    def apply(self, mutation: Mutation) -> GameSnapshot:
        if not isinstance(mutation, Mutation):
            raise StateMutationError("apply() requires a Mutation")
        if not mutation.updates:
            raise StateMutationError("empty mutation")
        with self._lock:
            if mutation.base_version != self._version:
                raise StaleVersionError(
                    f"mutation based on v{mutation.base_version}, state is v{self._version}")
            touched = set(mutation.updates) & self.protected_keys
            if touched:
                raise StateMutationError(f"protected keys: {sorted(touched)}")
            candidate = copy.deepcopy(self._data)
            candidate.update(copy.deepcopy(dict(mutation.updates)))
            for validate in self.validators:
                try:
                    validate(MappingProxyType(candidate), mutation)
                except StateMutationError:
                    raise
                except Exception as exc:  # validator bug or rejection
                    raise StateMutationError(f"validator rejected: {exc}") from exc
            self._data = candidate
            self._version += 1
            self._history.append((self._version, mutation.actor, mutation.reason, _digest(candidate)))
            return GameSnapshot(self._version, _freeze(copy.deepcopy(candidate)), _digest(candidate))
