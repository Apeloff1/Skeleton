"""Transactional state with invariant checks and rollback."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

Invariant = Callable[[dict[str, Any]], bool]

@dataclass(frozen=True, slots=True)
class TransactionResult:
    committed: bool
    version: int
    violations: tuple[str, ...]

class StateTransaction:
    def __init__(self, initial: dict[str, Any] | None = None, *, invariants: dict[str, Invariant] | None = None) -> None:
        self._state = deepcopy(initial or {})
        self._invariants = dict(invariants or {})
        self.version = 0
        self._snapshot = deepcopy(self._state)

    @property
    def state(self) -> dict[str, Any]:
        return deepcopy(self._state)

    def begin(self) -> None:
        self._snapshot = deepcopy(self._state)

    def set(self, key: str, value: Any) -> None:
        self._state[str(key)] = deepcopy(value)

    def update(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def check(self) -> tuple[str, ...]:
        failures = []
        for name, invariant in sorted(self._invariants.items()):
            try:
                ok = bool(invariant(deepcopy(self._state)))
            except Exception:
                ok = False
            if not ok:
                failures.append(name)
        return tuple(failures)

    def commit(self) -> TransactionResult:
        violations = self.check()
        if violations:
            self.rollback()
            return TransactionResult(False, self.version, violations)
        self.version += 1
        self._snapshot = deepcopy(self._state)
        return TransactionResult(True, self.version, ())

    def rollback(self) -> None:
        self._state = deepcopy(self._snapshot)

    def atomic(self, mutator: Callable[["StateTransaction"], None]) -> TransactionResult:
        self.begin()
        try:
            mutator(self)
        except Exception:
            self.rollback()
            raise
        return self.commit()

__all__ = ["StateTransaction", "TransactionResult"]
