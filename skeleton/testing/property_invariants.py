"""Deterministic property/invariant campaign primitives for VOL-199."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
from typing import Callable, Generic, Iterable, Mapping, Sequence, TypeVar

T = TypeVar("T")


class PropertyContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Invariant:
    name: str
    state_machine: str
    statement: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.state_machine.strip() or not self.statement.strip():
            raise PropertyContractError("invariant fields must be non-empty")


@dataclass(frozen=True, slots=True)
class GeneratedCase(Generic[T]):
    seed: int
    index: int
    value: T


@dataclass(frozen=True, slots=True)
class Counterexample(Generic[T]):
    invariant: str
    state_machine: str
    seed: int
    index: int
    original: T
    minimal: T
    digest: str


@dataclass(frozen=True, slots=True)
class Property(Generic[T]):
    name: str
    invariant: str
    generator: Callable[[random.Random], T]
    predicate: Callable[[T], bool]
    shrinker: Callable[[T], Iterable[T]] = lambda _: ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.invariant.strip():
            raise PropertyContractError("property name and invariant are required")


class InvariantRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Invariant] = {}

    def register(self, invariant: Invariant) -> Invariant:
        if invariant.name in self._items:
            raise PropertyContractError(f"duplicate invariant: {invariant.name}")
        self._items[invariant.name] = invariant
        return invariant

    def require(self, name: str) -> Invariant:
        try:
            return self._items[name]
        except KeyError as exc:
            raise PropertyContractError(f"unknown invariant: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))


class PropertyCampaign:
    """Runs bounded reproducible cases and deterministically shrinks failures."""

    def __init__(self, registry: InvariantRegistry, *, max_cases: int = 1000, max_shrinks: int = 128) -> None:
        if not 1 <= max_cases <= 100_000:
            raise PropertyContractError("max_cases outside safe bounds")
        if not 0 <= max_shrinks <= 10_000:
            raise PropertyContractError("max_shrinks outside safe bounds")
        self.registry = registry
        self.max_cases = max_cases
        self.max_shrinks = max_shrinks

    def run(self, prop: Property[T], *, seed: int, cases: int | None = None) -> Counterexample[T] | None:
        invariant = self.registry.require(prop.invariant)
        count = self.max_cases if cases is None else cases
        if not 1 <= count <= self.max_cases:
            raise PropertyContractError("requested cases exceed campaign budget")
        rng = random.Random(seed)
        for index in range(count):
            value = prop.generator(rng)
            if not self._holds(prop, value):
                minimal = self._shrink(prop, value)
                payload = {
                    "schema": "skeleton.property-counterexample.v1",
                    "property": prop.name,
                    "invariant": invariant.name,
                    "state_machine": invariant.state_machine,
                    "seed": seed,
                    "index": index,
                    "minimal": repr(minimal),
                }
                digest = hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                return Counterexample(
                    invariant=invariant.name,
                    state_machine=invariant.state_machine,
                    seed=seed,
                    index=index,
                    original=value,
                    minimal=minimal,
                    digest=digest,
                )
        return None

    @staticmethod
    def _holds(prop: Property[T], value: T) -> bool:
        result = prop.predicate(value)
        if not isinstance(result, bool):
            raise PropertyContractError("property predicate must return bool")
        return result

    def _shrink(self, prop: Property[T], initial: T) -> T:
        current = initial
        seen = {repr(initial)}
        attempts = 0
        while attempts < self.max_shrinks:
            improved = False
            for candidate in prop.shrinker(current):
                attempts += 1
                if attempts > self.max_shrinks:
                    break
                marker = repr(candidate)
                if marker in seen:
                    continue
                seen.add(marker)
                if not self._holds(prop, candidate):
                    current = candidate
                    improved = True
                    break
            if not improved:
                break
        return current


def integer_toward_zero(value: int) -> Sequence[int]:
    """Stable shrink sequence for integer counterexamples."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PropertyContractError("integer shrinker requires int")
    if value == 0:
        return ()
    sign = 1 if value > 0 else -1
    magnitude = abs(value)
    candidates = [0]
    while magnitude > 1:
        magnitude //= 2
        candidates.append(sign * magnitude)
    return tuple(dict.fromkeys(candidates))


__all__ = [
    "Counterexample",
    "GeneratedCase",
    "Invariant",
    "InvariantRegistry",
    "Property",
    "PropertyCampaign",
    "PropertyContractError",
    "integer_toward_zero",
]
