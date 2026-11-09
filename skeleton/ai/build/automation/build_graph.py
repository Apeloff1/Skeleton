"""Dependency-aware planning graph for autonomous feature builds.

Architecture model output may describe relationships between planned files. The
host converts those relationships into a deterministic graph. Strongly connected
planned files remain in one implementation component, component dependencies are
ordered before dependants, and components are packed into a bounded number of
model shards without allowing model text to choose execution behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Iterable, Mapping, Sequence

from .build_contracts import ArchitecturePlan
from .supervisor_runtime import canonical_json


class BuildGraphError(ValueError):
    """An architecture dependency graph violated a host invariant."""


@dataclass(frozen=True, slots=True)
class BuildNode:
    path: str
    planned_dependencies: tuple[str, ...]
    external_dependencies: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "planned_dependencies": list(self.planned_dependencies),
            "external_dependencies": list(self.external_dependencies),
        }


@dataclass(frozen=True, slots=True)
class BuildComponent:
    component_id: str
    paths: tuple[str, ...]
    depends_on: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.component_id.startswith("component_"):
            raise BuildGraphError("invalid component identity")
        if not self.paths:
            raise BuildGraphError("build component must contain paths")
        if tuple(sorted(self.paths)) != self.paths:
            raise BuildGraphError("component paths must be sorted")
        if tuple(sorted(set(self.depends_on))) != self.depends_on:
            raise BuildGraphError(
                "component dependencies must be sorted and unique"
            )
        if self.component_id in self.depends_on:
            raise BuildGraphError("component cannot depend on itself")

    def as_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "paths": list(self.paths),
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True, slots=True)
class BuildShard:
    shard_id: str
    paths: tuple[str, ...]
    component_ids: tuple[str, ...]
    predecessor_shards: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.shard_id.startswith("build_shard_"):
            raise BuildGraphError("invalid build shard identity")
        if not self.paths:
            raise BuildGraphError("build shard must contain paths")
        if len(self.paths) != len(set(self.paths)):
            raise BuildGraphError("build shard contains duplicate paths")
        if self.shard_id in self.predecessor_shards:
            raise BuildGraphError("shard cannot depend on itself")

    def as_dict(self) -> dict[str, object]:
        return {
            "shard_id": self.shard_id,
            "paths": list(self.paths),
            "component_ids": list(self.component_ids),
            "predecessor_shards": list(self.predecessor_shards),
        }


@dataclass(frozen=True, slots=True)
class BuildGraph:
    nodes: tuple[BuildNode, ...]
    components: tuple[BuildComponent, ...]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(self.as_dict())
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "nodes": [node.as_dict() for node in self.nodes],
            "components": [
                component.as_dict()
                for component in self.components
            ],
        }

    @classmethod
    def from_architecture(
        cls,
        architecture: ArchitecturePlan,
    ) -> "BuildGraph":
        paths = {intent.path for intent in architecture.files}
        nodes = []
        edges: dict[str, tuple[str, ...]] = {}

        for intent in architecture.files:
            planned = tuple(
                sorted(
                    dependency
                    for dependency in intent.dependencies
                    if dependency in paths
                    and dependency != intent.path
                )
            )
            external = tuple(
                sorted(
                    dependency
                    for dependency in intent.dependencies
                    if dependency not in paths
                )
            )
            nodes.append(
                BuildNode(
                    path=intent.path,
                    planned_dependencies=planned,
                    external_dependencies=external,
                )
            )
            edges[intent.path] = planned

        nodes.sort(key=lambda item: item.path)
        components_raw = _strongly_connected_components(
            tuple(sorted(paths)),
            edges,
        )
        component_for: dict[str, str] = {}
        for index, component_paths in enumerate(
            components_raw,
            start=1,
        ):
            identity = f"component_{index:03d}"
            for path in component_paths:
                component_for[path] = identity

        components: list[BuildComponent] = []
        for index, component_paths in enumerate(
            components_raw,
            start=1,
        ):
            identity = f"component_{index:03d}"
            dependencies = set()
            for path in component_paths:
                for dependency in edges.get(path, ()):
                    target = component_for[dependency]
                    if target != identity:
                        dependencies.add(target)
            components.append(
                BuildComponent(
                    component_id=identity,
                    paths=component_paths,
                    depends_on=tuple(sorted(dependencies)),
                )
            )

        ordered = _topological_components(tuple(components))
        return cls(
            nodes=tuple(nodes),
            components=ordered,
        )

    def shards(
        self,
        *,
        max_shards: int,
    ) -> tuple[BuildShard, ...]:
        """Pack topologically ordered SCCs into at most max_shards shards."""
        if (
            isinstance(max_shards, bool)
            or not isinstance(max_shards, int)
            or max_shards < 1
            or max_shards > 32
        ):
            raise BuildGraphError("invalid build shard budget")
        if not self.components:
            return ()

        total_paths = sum(
            len(component.paths)
            for component in self.components
        )
        target = max(1, math.ceil(total_paths / max_shards))

        raw_shards: list[list[BuildComponent]] = []
        current: list[BuildComponent] = []
        current_paths = 0

        for component in self.components:
            component_size = len(component.paths)
            can_split = len(raw_shards) < max_shards - 1
            if (
                current
                and can_split
                and current_paths + component_size > target
            ):
                raw_shards.append(current)
                current = []
                current_paths = 0
            current.append(component)
            current_paths += component_size
        if current:
            raw_shards.append(current)

        component_to_shard: dict[str, str] = {}
        for index, items in enumerate(raw_shards, start=1):
            shard_id = f"build_shard_{index:03d}"
            for component in items:
                component_to_shard[component.component_id] = shard_id

        shards = []
        for index, items in enumerate(raw_shards, start=1):
            shard_id = f"build_shard_{index:03d}"
            paths = tuple(
                path
                for component in items
                for path in component.paths
            )
            predecessor = set()
            for component in items:
                for dependency in component.depends_on:
                    dependency_shard = component_to_shard[dependency]
                    if dependency_shard != shard_id:
                        predecessor.add(dependency_shard)
            shards.append(
                BuildShard(
                    shard_id=shard_id,
                    paths=paths,
                    component_ids=tuple(
                        component.component_id
                        for component in items
                    ),
                    predecessor_shards=tuple(
                        sorted(predecessor)
                    ),
                )
            )
        return tuple(shards)

    def dependency_closure(
        self,
        paths: Iterable[str],
    ) -> tuple[str, ...]:
        """Return planned transitive dependencies for a path set."""
        by_path = {node.path: node for node in self.nodes}
        pending = list(paths)
        seen: set[str] = set()
        while pending:
            path = pending.pop()
            node = by_path.get(path)
            if node is None:
                continue
            for dependency in node.planned_dependencies:
                if dependency in seen:
                    continue
                seen.add(dependency)
                pending.append(dependency)
        return tuple(sorted(seen))


def _strongly_connected_components(
    paths: Sequence[str],
    edges: Mapping[str, Sequence[str]],
) -> tuple[tuple[str, ...], ...]:
    """Tarjan SCC with deterministic traversal and deterministic identities."""
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for dependency in sorted(edges.get(node, ())):
            if dependency not in indices:
                visit(dependency)
                lowlinks[node] = min(
                    lowlinks[node],
                    lowlinks[dependency],
                )
            elif dependency in on_stack:
                lowlinks[node] = min(
                    lowlinks[node],
                    indices[dependency],
                )

        if lowlinks[node] != indices[node]:
            return

        component: list[str] = []
        while True:
            current = stack.pop()
            on_stack.remove(current)
            component.append(current)
            if current == node:
                break
        result.append(tuple(sorted(component)))

    for path in sorted(paths):
        if path not in indices:
            visit(path)

    result.sort(key=lambda group: group[0])
    return tuple(result)


def _topological_components(
    components: Sequence[BuildComponent],
) -> tuple[BuildComponent, ...]:
    """Order dependency components before dependants, stably by component ID."""
    by_id = {
        component.component_id: component
        for component in components
    }
    indegree = {
        component.component_id: len(component.depends_on)
        for component in components
    }
    dependants: dict[str, set[str]] = {
        component.component_id: set()
        for component in components
    }
    for component in components:
        for dependency in component.depends_on:
            if dependency not in by_id:
                raise BuildGraphError(
                    "component references unknown dependency"
                )
            dependants[dependency].add(component.component_id)

    ready = sorted(
        identity
        for identity, count in indegree.items()
        if count == 0
    )
    ordered: list[BuildComponent] = []

    while ready:
        identity = ready.pop(0)
        ordered.append(by_id[identity])
        for dependant in sorted(dependants[identity]):
            indegree[dependant] -= 1
            if indegree[dependant] == 0:
                ready.append(dependant)
                ready.sort()

    if len(ordered) != len(components):
        raise BuildGraphError(
            "component condensation graph unexpectedly contains a cycle"
        )
    return tuple(ordered)
