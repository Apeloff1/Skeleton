"""Deterministic dependency planning and conflict-free execution batches."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping

from .canonical import digest
from .errors import (
    ScheduleCycleError,
    ScheduleError,
    SystemConflictError,
    SystemNotFoundError,
)

MAX_SYSTEMS = 10_000
MAX_DEPENDENCIES = 100_000


class SystemPhase(IntEnum):
    PRE = 10
    UPDATE = 20
    POST = 30


@dataclass(frozen=True)
class SystemSpec:
    system_id: str
    phase: SystemPhase = SystemPhase.UPDATE
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.system_id, str) or not self.system_id:
            raise ScheduleError("system id required")
        if not isinstance(self.phase, SystemPhase):
            object.__setattr__(self, "phase", SystemPhase(self.phase))
        if not isinstance(self.enabled, bool):
            raise ScheduleError("system enabled flag must be boolean")
        for name in ("reads", "writes", "after", "before"):
            values = tuple(sorted(set(getattr(self, name))))
            object.__setattr__(self, name, values)
        if set(self.reads) & set(self.writes):
            object.__setattr__(
                self,
                "reads",
                tuple(value for value in self.reads if value not in self.writes),
            )


@dataclass(frozen=True)
class ExecutionBatch:
    index: int
    system_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    ordered_system_ids: tuple[str, ...]
    batches: tuple[ExecutionBatch, ...]
    dependencies: Mapping[str, tuple[str, ...]]
    fingerprint: str


def conflicts(first: SystemSpec, second: SystemSpec) -> bool:
    first_writes = set(first.writes)
    second_writes = set(second.writes)
    first_reads = set(first.reads)
    second_reads = set(second.reads)
    return bool(
        (first_writes & second_writes)
        | (first_writes & second_reads)
        | (second_writes & first_reads)
    )


class SystemGraph:
    def __init__(self) -> None:
        self._systems: dict[str, SystemSpec] = {}

    def register(self, spec: SystemSpec) -> SystemSpec:
        if not isinstance(spec, SystemSpec):
            raise ScheduleError("register requires SystemSpec")
        if len(self._systems) >= MAX_SYSTEMS and spec.system_id not in self._systems:
            raise ScheduleError("system bound exceeded")
        prior = self._systems.get(spec.system_id)
        if prior is not None and prior != spec:
            raise SystemConflictError(
                "system id conflict",
                context={"system_id": spec.system_id},
            )
        self._systems[spec.system_id] = spec
        return spec

    def get(self, system_id: str) -> SystemSpec:
        if system_id not in self._systems:
            raise SystemNotFoundError(
                "system not found",
                context={"system_id": system_id},
            )
        return self._systems[system_id]

    def system_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._systems))

    def enabled_system_ids(self) -> tuple[str, ...]:
        return tuple(
            system_id
            for system_id in sorted(self._systems)
            if self._systems[system_id].enabled
        )

    def _dependencies(self) -> dict[str, set[str]]:
        dependencies: dict[str, set[str]] = {
            system_id: set() for system_id in self._systems
        }
        explicit_edges = 0
        for system_id, spec in self._systems.items():
            for dependency in spec.after:
                if dependency not in self._systems:
                    raise SystemNotFoundError(
                        "after dependency not found",
                        context={
                            "system_id": system_id,
                            "dependency": dependency,
                        },
                    )
                dependencies[system_id].add(dependency)
                explicit_edges += 1
            for target in spec.before:
                if target not in self._systems:
                    raise SystemNotFoundError(
                        "before dependency not found",
                        context={"system_id": system_id, "dependency": target},
                    )
                dependencies[target].add(system_id)
                explicit_edges += 1

        ids = sorted(self._systems)
        for index, first_id in enumerate(ids):
            first = self._systems[first_id]
            for second_id in ids[index + 1 :]:
                second = self._systems[second_id]
                if first.phase < second.phase:
                    dependencies[second_id].add(first_id)
                elif second.phase < first.phase:
                    dependencies[first_id].add(second_id)

        edge_count = sum(len(values) for values in dependencies.values())
        if edge_count > MAX_DEPENDENCIES or explicit_edges > MAX_DEPENDENCIES:
            raise ScheduleError("dependency bound exceeded")
        return dependencies

    def plan(self) -> ExecutionPlan:
        all_dependencies = self._dependencies()
        enabled = set(self.enabled_system_ids())

        # Disabled systems are declarative nodes, not executable barriers.  Any
        # dependency on a disabled node is treated as already satisfied for the
        # executable plan, while unknown dependency names still fail above.
        remaining: dict[str, set[str]] = {
            system_id: {
                dependency
                for dependency in all_dependencies[system_id]
                if dependency in enabled
            }
            for system_id in sorted(enabled)
        }
        executable_dependencies = {
            system_id: tuple(sorted(dependencies))
            for system_id, dependencies in sorted(remaining.items())
        }

        ordered: list[str] = []
        batches: list[ExecutionBatch] = []
        while remaining:
            ready = sorted(
                (system_id for system_id, deps in remaining.items() if not deps),
                key=lambda system_id: (
                    self._systems[system_id].phase,
                    system_id,
                ),
            )
            if not ready:
                raise ScheduleCycleError(
                    "system dependency cycle",
                    context={"remaining": sorted(remaining)},
                )

            batch: list[str] = []
            for system_id in ready:
                if any(
                    conflicts(self._systems[system_id], self._systems[other])
                    for other in batch
                ):
                    continue
                batch.append(system_id)

            # At least the lexicographically first ready system is always safe
            # to execute by itself, so this guard mainly documents the planner
            # invariant and protects future conflict policy changes.
            if not batch:
                batch = [ready[0]]

            batches.append(ExecutionBatch(len(batches), tuple(batch)))
            for system_id in batch:
                ordered.append(system_id)
                remaining.pop(system_id)
            for dependencies in remaining.values():
                dependencies.difference_update(batch)

        fingerprint = digest(
            {
                "domain": "skeleton.simulation.ecs.execution_plan.v1",
                "ordered": ordered,
                "batches": [batch.system_ids for batch in batches],
                "dependencies": executable_dependencies,
            }
        )
        return ExecutionPlan(
            ordered_system_ids=tuple(ordered),
            batches=tuple(batches),
            dependencies=executable_dependencies,
            fingerprint=fingerprint,
        )
