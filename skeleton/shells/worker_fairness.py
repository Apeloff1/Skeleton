"""Fair-share scheduling primitives for multi-principal worker queues."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
from types import MappingProxyType
from typing import Generic, Mapping, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class FairSharePolicy:
    default_weight: int = 1
    max_weight: int = 100
    quantum: int = 1
    max_principals: int = 4096
    max_items_per_principal: int = 10000

    def __post_init__(self) -> None:
        if self.default_weight <= 0:
            raise ValueError("default_weight must be positive")
        if self.max_weight < self.default_weight:
            raise ValueError("max_weight must be >= default_weight")
        if self.quantum <= 0:
            raise ValueError("quantum must be positive")
        if self.max_principals <= 0 or self.max_items_per_principal <= 0:
            raise ValueError("fair-share bounds must be positive")


@dataclass(frozen=True)
class FairShareStats:
    principal: str
    weight: int
    queued: int
    deficit: int
    dispatched: int

    def to_dict(self) -> dict[str, object]:
        return {
            "principal": self.principal,
            "weight": self.weight,
            "queued": self.queued,
            "deficit": self.deficit,
            "dispatched": self.dispatched,
        }


@dataclass(frozen=True)
class FairShareSnapshot:
    principals: tuple[FairShareStats, ...]
    total_queued: int
    total_dispatched: int

    def to_dict(self) -> dict[str, object]:
        return {
            "total_queued": self.total_queued,
            "total_dispatched": self.total_dispatched,
            "principals": [item.to_dict() for item in self.principals],
        }


@dataclass
class _PrincipalState(Generic[T]):
    weight: int
    queue: deque[tuple[T, int]]
    deficit: int = 0
    dispatched: int = 0


class DeficitFairQueue(Generic[T]):
    """Bounded deficit-round-robin queue.

    Cost is explicit per item, allowing expensive worker tasks to consume a
    larger share of a principal's deficit without starving small jobs.
    """

    def __init__(self, policy: FairSharePolicy | None = None) -> None:
        self.policy = policy or FairSharePolicy()
        self._states: dict[str, _PrincipalState[T]] = {}
        self._order: deque[str] = deque()
        self._weights: dict[str, int] = {}
        self._total_dispatched = 0
        self._lock = threading.RLock()

    @staticmethod
    def _principal(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError("invalid fair-share principal")
        return value

    def set_weight(self, principal: str, weight: int) -> None:
        principal = self._principal(principal)
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("weight must be an integer")
        if weight <= 0 or weight > self.policy.max_weight:
            raise ValueError("weight outside supported bounds")
        with self._lock:
            self._weights[principal] = weight
            state = self._states.get(principal)
            if state is not None:
                state.weight = weight

    def _ensure(self, principal: str) -> _PrincipalState[T]:
        state = self._states.get(principal)
        if state is not None:
            return state
        if len(self._states) >= self.policy.max_principals:
            raise RuntimeError("fair-share principal capacity exhausted")
        weight = self._weights.get(principal, self.policy.default_weight)
        state = _PrincipalState(weight=weight, queue=deque())
        self._states[principal] = state
        self._order.append(principal)
        return state

    def enqueue(self, principal: str, item: T, *, cost: int = 1) -> None:
        principal = self._principal(principal)
        if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
            raise ValueError("cost must be a positive integer")
        with self._lock:
            state = self._ensure(principal)
            if len(state.queue) >= self.policy.max_items_per_principal:
                raise RuntimeError("fair-share principal queue capacity exhausted")
            state.queue.append((item, cost))

    def _drop_empty_front(self) -> None:
        rounds = len(self._order)
        for _ in range(rounds):
            principal = self._order[0]
            state = self._states[principal]
            if state.queue:
                break
            self._order.rotate(-1)

    def pop(self) -> tuple[str, T] | None:
        with self._lock:
            if not any(state.queue for state in self._states.values()):
                return None
            max_turns = max(1, len(self._states) * 1000)
            for _ in range(max_turns):
                self._drop_empty_front()
                principal = self._order[0]
                state = self._states[principal]
                if not state.queue:
                    return None
                state.deficit += self.policy.quantum * state.weight
                item, cost = state.queue[0]
                if cost <= state.deficit:
                    state.queue.popleft()
                    state.deficit -= cost
                    state.dispatched += 1
                    self._total_dispatched += 1
                    self._order.rotate(-1)
                    return principal, item
                self._order.rotate(-1)
            raise RuntimeError("fair-share scheduler made no progress; item costs exceed effective quantum")

    def peek_principals(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                principal
                for principal in self._order
                if self._states[principal].queue
            )

    def remove_principal(self, principal: str, *, require_empty: bool = True) -> bool:
        principal = self._principal(principal)
        with self._lock:
            state = self._states.get(principal)
            if state is None:
                return False
            if require_empty and state.queue:
                raise RuntimeError("cannot remove non-empty principal")
            del self._states[principal]
            self._weights.pop(principal, None)
            self._order = deque(value for value in self._order if value != principal)
            return True

    def queued(self, principal: str | None = None) -> int:
        with self._lock:
            if principal is None:
                return sum(len(state.queue) for state in self._states.values())
            state = self._states.get(principal)
            return 0 if state is None else len(state.queue)

    def snapshot(self) -> FairShareSnapshot:
        with self._lock:
            rows = tuple(
                FairShareStats(
                    principal=principal,
                    weight=state.weight,
                    queued=len(state.queue),
                    deficit=state.deficit,
                    dispatched=state.dispatched,
                )
                for principal, state in sorted(self._states.items())
            )
            return FairShareSnapshot(
                principals=rows,
                total_queued=sum(row.queued for row in rows),
                total_dispatched=self._total_dispatched,
            )
