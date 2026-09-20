"""Dependency and subsystem graph algorithms for repository intelligence."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .model import DependencyEdge, FileRecord, Subsystem, SubsystemStats


@dataclass(frozen=True, slots=True)
class GraphMetrics:
    node_count: int
    edge_count: int
    internal_edge_count: int
    external_edge_count: int
    cycle_count: int
    largest_cycle: int
    orphan_count: int
    max_fan_in: int
    max_fan_out: int


@dataclass(frozen=True, slots=True)
class GraphView:
    adjacency: Mapping[str, tuple[str, ...]]
    reverse: Mapping[str, tuple[str, ...]]
    fan_in: Mapping[str, int]
    fan_out: Mapping[str, int]
    cycles: tuple[tuple[str, ...], ...]
    orphans: tuple[str, ...]
    metrics: GraphMetrics


def build_adjacency(
    edges: Iterable[DependencyEdge],
    *,
    internal_only: bool = True,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if internal_only and edge.external:
            continue
        forward[edge.source].add(edge.target)
        reverse[edge.target].add(edge.source)
        forward.setdefault(edge.target, set())
        reverse.setdefault(edge.source, set())
    return (
        {key: tuple(sorted(value)) for key, value in sorted(forward.items())},
        {key: tuple(sorted(value)) for key, value in sorted(reverse.items())},
    )


def strongly_connected_components(
    adjacency: Mapping[str, Sequence[str]],
) -> tuple[tuple[str, ...], ...]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[tuple[str, ...]] = []

    for root in sorted(adjacency):
        if root in indices:
            continue
        frames: list[tuple[str, int, bool]] = [(root, 0, False)]
        parent: dict[str, str] = {}
        while frames:
            node, child_index, entered = frames.pop()
            neighbors = adjacency.get(node, ())
            if not entered:
                if node in indices:
                    continue
                indices[node] = index
                lowlinks[node] = index
                index += 1
                stack.append(node)
                on_stack.add(node)
                entered = True

            if child_index < len(neighbors):
                target = neighbors[child_index]
                frames.append((node, child_index + 1, True))
                if target not in indices:
                    parent[target] = node
                    frames.append((target, 0, False))
                elif target in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[target])
                continue

            for target in neighbors:
                if parent.get(target) == node:
                    lowlinks[node] = min(lowlinks[node], lowlinks[target])

            if lowlinks[node] == indices[node]:
                component: list[str] = []
                while stack:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(tuple(sorted(component)))

    components.sort(key=lambda item: (-len(item), item))
    return tuple(components)


def cycles(adjacency: Mapping[str, Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    components = strongly_connected_components(adjacency)
    result: list[tuple[str, ...]] = []
    for component in components:
        if len(component) > 1:
            result.append(component)
            continue
        node = component[0]
        if node in adjacency.get(node, ()):
            result.append(component)
    return tuple(result)


def graph_view(
    files: Iterable[FileRecord],
    edges: Iterable[DependencyEdge],
) -> GraphView:
    files_tuple = tuple(files)
    edges_tuple = tuple(edges)
    adjacency, reverse = build_adjacency(edges_tuple)
    for file in files_tuple:
        if file.module_name is not None:
            adjacency.setdefault(file.path, ())
            reverse.setdefault(file.path, ())

    fan_in = {node: len(reverse.get(node, ())) for node in adjacency}
    fan_out = {node: len(adjacency.get(node, ())) for node in adjacency}
    cycle_set = cycles(adjacency)
    orphans = tuple(
        sorted(
            node
            for node in adjacency
            if not adjacency.get(node) and not reverse.get(node)
        )
    )
    internal = sum(1 for edge in edges_tuple if not edge.external)
    external = sum(1 for edge in edges_tuple if edge.external)
    return GraphView(
        adjacency=adjacency,
        reverse=reverse,
        fan_in=fan_in,
        fan_out=fan_out,
        cycles=cycle_set,
        orphans=orphans,
        metrics=GraphMetrics(
            node_count=len(adjacency),
            edge_count=len(edges_tuple),
            internal_edge_count=internal,
            external_edge_count=external,
            cycle_count=len(cycle_set),
            largest_cycle=max((len(item) for item in cycle_set), default=0),
            orphan_count=len(orphans),
            max_fan_in=max(fan_in.values(), default=0),
            max_fan_out=max(fan_out.values(), default=0),
        ),
    )


def shortest_dependency_path(
    graph: GraphView,
    source: str,
    target: str,
    *,
    max_depth: int = 64,
) -> tuple[str, ...] | None:
    if source == target:
        return (source,)
    if source not in graph.adjacency or target not in graph.adjacency:
        return None
    queue = deque([(source, (source,))])
    visited = {source}
    while queue:
        node, path = queue.popleft()
        if len(path) > max_depth:
            continue
        for child in graph.adjacency.get(node, ()):
            if child == target:
                return (*path, child)
            if child in visited:
                continue
            visited.add(child)
            queue.append((child, (*path, child)))
    return None


def transitive_dependents(
    graph: GraphView,
    target: str,
    *,
    limit: int = 5000,
) -> tuple[str, ...]:
    if target not in graph.reverse:
        return ()
    result: list[str] = []
    queue = deque(graph.reverse.get(target, ()))
    visited = set(queue)
    while queue and len(result) < limit:
        node = queue.popleft()
        result.append(node)
        for parent in graph.reverse.get(node, ()):
            if parent not in visited:
                visited.add(parent)
                queue.append(parent)
    return tuple(result)


def subsystem_dependency_edges(
    files: Iterable[FileRecord],
    edges: Iterable[DependencyEdge],
) -> dict[tuple[str, str], int]:
    file_map = {item.path: item for item in files}
    counts: Counter[tuple[str, str]] = Counter()
    for edge in edges:
        if edge.external:
            continue
        source = file_map.get(edge.source)
        target = file_map.get(edge.target)
        if source is None or target is None:
            continue
        if source.subsystem_id is None or target.subsystem_id is None:
            continue
        if source.subsystem_id == target.subsystem_id:
            continue
        counts[(source.subsystem_id, target.subsystem_id)] += 1
    return dict(sorted(counts.items()))


def subsystem_stats(
    files: Iterable[FileRecord],
    edges: Iterable[DependencyEdge],
    subsystems: Iterable[Subsystem],
    graph: GraphView | None = None,
) -> tuple[SubsystemStats, ...]:
    materialized = tuple(files)
    subsystem_ids = {item.id for item in subsystems}
    out_counts: Counter[str] = Counter()
    in_counts: Counter[str] = Counter()
    file_map = {item.path: item for item in materialized}
    for edge in edges:
        if edge.external:
            continue
        source = file_map.get(edge.source)
        target = file_map.get(edge.target)
        if source and source.subsystem_id:
            out_counts[source.subsystem_id] += 1
        if target and target.subsystem_id:
            in_counts[target.subsystem_id] += 1

    orphan_paths = set(graph.orphans if graph else ())
    records: list[SubsystemStats] = []
    for subsystem_id in sorted(subsystem_ids):
        owned = [item for item in materialized if item.subsystem_id == subsystem_id]
        records.append(
            SubsystemStats(
                subsystem_id=subsystem_id,
                files=len(owned),
                source_files=sum(1 for item in owned if item.role.value == "source"),
                test_files=sum(1 for item in owned if item.role.value == "test"),
                docs_files=sum(1 for item in owned if item.role.value == "doc"),
                lines=sum(item.lines or 0 for item in owned),
                bytes=sum(item.size_bytes for item in owned),
                imports_out=out_counts[subsystem_id],
                imports_in=in_counts[subsystem_id],
                parse_errors=sum(1 for item in owned if item.parse_error),
                todos=sum(len(item.todos) for item in owned),
                orphan_files=sum(1 for item in owned if item.path in orphan_paths),
            )
        )
    return tuple(records)


def declared_dependency_findings(
    files: Iterable[FileRecord],
    edges: Iterable[DependencyEdge],
    subsystems: Iterable[Subsystem],
) -> tuple[str, ...]:
    declared = {item.id: set(item.depends_on) for item in subsystems}
    file_map = {item.path: item for item in files}
    findings: set[str] = set()
    for edge in edges:
        if edge.external:
            continue
        source = file_map.get(edge.source)
        target = file_map.get(edge.target)
        if not source or not target:
            continue
        if not source.subsystem_id or not target.subsystem_id:
            continue
        if source.subsystem_id == target.subsystem_id:
            continue
        allowed = declared.get(source.subsystem_id, set())
        if target.subsystem_id not in allowed:
            findings.add(
                "undeclared-subsystem-edge:"
                f"{source.subsystem_id}->{target.subsystem_id}:"
                f"{edge.source}:{edge.line or 0}"
            )
    return tuple(sorted(findings))
