"""Authoritative game state: the only mutation path is a guarded, validated,
versioned ``apply``. Readers only ever get immutable snapshots."""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping


class StateMutationError(ValueError):
    """Raised when a mutation fails validation; state is left untouched."""


class StaleVersionError(StateMutationError):
    """Raised when a mutation was computed against an older version."""


MAX_STATE_BYTES = 1 * 1024 * 1024
MAX_FIELDS = 4096
MAX_HISTORY = 10000
MAX_DEPTH = 32
MAX_ITEMS = 50000


def _check(value: Any, *, depth: int = 0, budget: list[int] | None = None,
           visited: set[int] | None = None) -> None:
    """Reject aliases, cycles, nonfinite values, non-JSON and oversized state."""
    if budget is None:
        budget = [0]
    if visited is None:
        visited = set()
    budget[0] += 1
    if budget[0] > MAX_ITEMS or depth > MAX_DEPTH:
        raise StateMutationError("game state depth or item budget exceeded")
    if value is None or type(value) in (bool, int):
        if type(value) is int and value.bit_length() > 256:
            raise StateMutationError("game state integer too large")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise StateMutationError("game state contains nonfinite number")
        return
    if type(value) is str:
        if len(value) > 16384:
            raise StateMutationError("game state text exceeds bound")
        return
    if type(value) not in (dict, list, tuple):
        raise StateMutationError("game state requires strict JSON values")
    obj_id = id(value)
    if obj_id in visited:
        raise StateMutationError("game state contains recursive reference")
    visited.add(obj_id)
    try:
        if len(value) > MAX_FIELDS:
            raise StateMutationError("game state container too large")
        if type(value) is dict:
            if any(type(key) is not str or not 1 <= len(key) <= 256 for key in value):
                raise StateMutationError("game state key must be bounded text")
            for child in value.values():
                _check(child, depth=depth+1, budget=budget, visited=visited)
        else:
            for child in value:
                _check(child, depth=depth+1, budget=budget, visited=visited)
    finally:
        visited.remove(obj_id)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return value


def _digest(data: Mapping[str, Any]) -> str:
    _check(data)
    try:
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise StateMutationError("state is not canonical JSON") from exc
    if len(raw) > MAX_STATE_BYTES:
        raise StateMutationError("state exceeds encoded byte quota")
    return hashlib.sha256(raw).hexdigest()


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
        if not isinstance(self.initial, Mapping) or not isinstance(self.validators, list):
            raise StateMutationError("invalid state or validator inventory")
        if not isinstance(self.protected_keys, frozenset):
            raise StateMutationError("protected keys must be a frozenset")
        if any(not callable(v) for v in self.validators):
            raise StateMutationError("all validators must be callable")
        self._data: dict[str, Any] = copy.deepcopy(dict(self.initial))
        initial_digest = _digest(self._data)
        self._version = 0
        self._lock = threading.Lock()
        self._history: list[tuple[int, str, str, str]] = [(0, "init", "", initial_digest)]

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
        if (type(mutation.base_version) is not int or mutation.base_version < 0
                or not isinstance(mutation.updates, Mapping)
                or not 1 <= len(mutation.updates) <= MAX_FIELDS):
            raise StateMutationError("invalid bounded mutation envelope")
        if (type(mutation.actor) is not str or not 1 <= len(mutation.actor) <= 128
                or type(mutation.reason) is not str or len(mutation.reason) > 256):
            raise StateMutationError("unbounded mutation identity or reason")
        try:
            delta = copy.deepcopy(dict(mutation.updates))
        except (TypeError, ValueError, RecursionError) as exc:
            raise StateMutationError("invalid mutation values") from exc
        _check(delta)
        with self._lock:
            if mutation.base_version != self._version:
                raise StaleVersionError(
                    f"mutation based on v{mutation.base_version}, state is v{self._version}")
            touched = set(delta) & self.protected_keys
            if touched:
                raise StateMutationError(f"protected keys: {sorted(touched)}")
            if len(self._history) >= MAX_HISTORY:
                raise StateMutationError("state history retention budget exhausted")
            candidate = copy.deepcopy(self._data)
            candidate.update(delta)
            # Complete all canonical/integrity checks before publishing ANY state.
            expected_digest = _digest(candidate)
            frozen = _freeze(copy.deepcopy(candidate))
            for validate in self.validators:
                try:
                    validate(frozen, mutation)
                except StateMutationError:
                    raise
                except Exception as exc:
                    raise StateMutationError("game state validator rejected mutation") from exc
            if _digest(candidate) != expected_digest:
                raise StateMutationError("validation unexpectedly modified candidate")
            new_version = self._version + 1
            rec = (new_version, mutation.actor, mutation.reason, expected_digest)
            result = GameSnapshot(new_version, frozen, expected_digest)
            self._data = candidate
            self._version = new_version
            self._history.append(rec)
            return result
