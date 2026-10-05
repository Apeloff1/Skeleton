"""Composable safety/resource guards for action execution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable

GuardFn = Callable[[object], bool]

@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    failed: tuple[str, ...]

class GuardChain:
    def __init__(self, guards: dict[str, GuardFn] | None = None) -> None:
        self._guards = dict(guards or {})

    def add(self, name: str, guard: GuardFn) -> None:
        if not name:
            raise ValueError("guard name required")
        self._guards[name] = guard

    def evaluate(self, value: object, *, only: Iterable[str] | None = None) -> GuardDecision:
        names = sorted(self._guards if only is None else set(only))
        failed: list[str] = []
        for name in names:
            guard = self._guards.get(name)
            if guard is None:
                failed.append(name)
                continue
            try:
                if not guard(value):
                    failed.append(name)
            except Exception:
                failed.append(name)
        return GuardDecision(not failed, tuple(failed))

    def require(self, value: object) -> None:
        decision = self.evaluate(value)
        if not decision.allowed:
            raise PermissionError("guards failed: " + ", ".join(decision.failed))

__all__ = ["GuardChain", "GuardDecision"]
