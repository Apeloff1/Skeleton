"""Intent-aware planner specialist registry for model handoff decisions."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.types import AIIntent, IntentKind


@dataclass(frozen=True)
class PlannerSpecialist:
    name: str
    model: AIModelPort
    intent_kinds: frozenset[IntentKind]
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128:
            raise ValueError("invalid specialist name")
        kinds = frozenset(IntentKind(item) for item in self.intent_kinds)
        if not kinds:
            raise ValueError("specialist must support at least one intent kind")
        object.__setattr__(self, "intent_kinds", kinds)


class SpecialistRegistry:
    """Select specialists deterministically; selection never changes shell authority."""

    def __init__(self, *, max_specialists: int = 128) -> None:
        if max_specialists <= 0:
            raise ValueError("max_specialists must be positive")
        self.max_specialists = max_specialists
        self._items: dict[str, PlannerSpecialist] = {}
        self._lock = threading.RLock()

    def register(self, specialist: PlannerSpecialist, *, replace: bool = False) -> None:
        with self._lock:
            if specialist.name in self._items and not replace:
                raise ValueError("specialist already registered")
            if specialist.name not in self._items and len(self._items) >= self.max_specialists:
                raise RuntimeError("specialist registry capacity exhausted")
            self._items[specialist.name] = specialist

    def route(self, intent: AIIntent) -> tuple[PlannerSpecialist, ...]:
        with self._lock:
            matches = [
                item for item in self._items.values()
                if intent.kind in item.intent_kinds
            ]
        matches.sort(key=lambda item: (-item.priority, item.name))
        return tuple(matches)

    def get(self, name: str) -> PlannerSpecialist:
        with self._lock:
            return self._items[name]
