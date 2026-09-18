"""Stable entity identity and bounded monotonic allocation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .canonical import digest
from .errors import BoundsError, IdentifierError

MAX_ENTITY_ID_CHARS = 128
MAX_NAMESPACE_CHARS = 64
MAX_ALLOCATIONS = 2**63 - 1

_ENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_entity_id(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise IdentifierError("entity id must be non-empty text")
    if len(value) > MAX_ENTITY_ID_CHARS or not _ENTITY_RE.fullmatch(value):
        raise IdentifierError("invalid entity id", context={"entity_id": value})
    return value


def validate_namespace(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise IdentifierError("namespace must be non-empty text")
    if len(value) > MAX_NAMESPACE_CHARS or not _NAMESPACE_RE.fullmatch(value):
        raise IdentifierError("invalid entity namespace", context={"namespace": value})
    return value


@dataclass(frozen=True, order=True)
class EntityId:
    """Typed entity id wrapper.

    The underlying value remains human-readable for logs and serialized state,
    while deterministic allocation uses a digest suffix so two worlds can
    allocate independently without relying on UUID randomness.
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validate_entity_id(self.value))

    def __str__(self) -> str:
        return self.value


class EntityAllocator:
    """Deterministic monotonic allocator.

    ``allocate()`` is deterministic for a namespace, seed and allocation
    counter.  The seed is part of state and must be snapshotted when callers
    need exact replay.
    """

    def __init__(self, namespace: str = "entity", *, seed: str = "default", counter: int = 0) -> None:
        self.namespace = validate_namespace(namespace)
        if not isinstance(seed, str) or not seed:
            raise IdentifierError("allocator seed must be non-empty text")
        if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
            raise IdentifierError("allocator counter must be a non-negative integer")
        if counter > MAX_ALLOCATIONS:
            raise BoundsError("allocator counter exceeds bound")
        self.seed = seed
        self.counter = counter

    def allocate(self, hint: str | None = None) -> EntityId:
        if self.counter >= MAX_ALLOCATIONS:
            raise BoundsError("entity allocator exhausted")
        if hint is not None:
            if not isinstance(hint, str) or not hint:
                raise IdentifierError("entity hint must be non-empty text")
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", hint.strip()).strip("-")
            if not safe:
                safe = "entity"
            safe = safe[:32]
        else:
            safe = "entity"
        sequence = self.counter
        suffix = digest(
            {
                "domain": "skeleton.simulation.ecs.entity_id.v1",
                "namespace": self.namespace,
                "seed": self.seed,
                "counter": sequence,
                "hint": hint,
            }
        )[:16]
        self.counter += 1
        return EntityId(f"{self.namespace}:{safe}:{sequence:016x}:{suffix}")

    def snapshot(self) -> dict[str, object]:
        return {
            "namespace": self.namespace,
            "seed": self.seed,
            "counter": self.counter,
        }

    @classmethod
    def restore(cls, record: dict[str, object]) -> "EntityAllocator":
        if not isinstance(record, dict):
            raise IdentifierError("allocator record must be a mapping")
        if set(record) != {"namespace", "seed", "counter"}:
            raise IdentifierError("allocator record has unexpected fields")
        return cls(
            namespace=record["namespace"],  # type: ignore[arg-type]
            seed=record["seed"],  # type: ignore[arg-type]
            counter=record["counter"],  # type: ignore[arg-type]
        )
