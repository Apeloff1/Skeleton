"""Fast deterministic topology-aware queries over RepositoryModel."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Iterable

from .model import FileRecord, RepositoryModel


@dataclass(frozen=True, slots=True)
class QueryResult:
    files: tuple[FileRecord, ...]
    zones: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "files": [item.as_dict() for item in self.files],
            "zones": list(self.zones),
            "reason": self.reason,
        }


class RepositoryQuery:
    def __init__(self, model: RepositoryModel) -> None:
        self.model = model
        self._by_zone: dict[str, tuple[FileRecord, ...]] = {}
        grouped: dict[str, list[FileRecord]] = defaultdict(list)
        for item in model.files:
            grouped[item.zone].append(item)
        self._by_zone = {zone: tuple(items) for zone, items in grouped.items()}
        self._by_kind: dict[str, tuple[FileRecord, ...]] = {}
        grouped_kind: dict[str, list[FileRecord]] = defaultdict(list)
        for item in model.files:
            grouped_kind[item.kind].append(item)
        self._by_kind = {kind: tuple(items) for kind, items in grouped_kind.items()}
        self._dependents: dict[str, tuple[str, ...]] = self._reverse_edges()
        self._dependencies: dict[str, tuple[str, ...]] = {
            item.name: tuple(sorted(set(item.dependencies)))
            for item in model.subsystems
        }

    def _reverse_edges(self) -> dict[str, tuple[str, ...]]:
        reverse: dict[str, set[str]] = defaultdict(set)
        for edge in self.model.edges:
            reverse[edge.target].add(edge.source)
        return {zone: tuple(sorted(values)) for zone, values in reverse.items()}

    def files(
        self,
        *,
        zones: Iterable[str] = (),
        kinds: Iterable[str] = (),
        languages: Iterable[str] = (),
        path_globs: Iterable[str] = (),
        limit: int = 200,
    ) -> QueryResult:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
            raise ValueError("limit must be in [1,5000]")
        zone_set = {str(item).casefold() for item in zones}
        kind_set = {str(item).casefold() for item in kinds}
        language_set = {str(item).casefold() for item in languages}
        globs = tuple(str(item) for item in path_globs if str(item))
        pools = [self._by_zone[z] for z in zone_set if z in self._by_zone]
        candidates = tuple(item for pool in pools for item in pool) if zone_set else self.model.files
        if not pools and zone_set:
            candidates = ()
        selected: list[FileRecord] = []
        for item in candidates:
            if kind_set and item.kind.casefold() not in kind_set:
                continue
            if language_set and item.language.casefold() not in language_set:
                continue
            if globs and not any(fnmatch(item.path, pattern) for pattern in globs):
                continue
            selected.append(item)
            if len(selected) >= limit:
                break
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "indexed-filter")

    def largest_files(self, *, zone: str = "", limit: int = 25) -> QueryResult:
        values = self._by_zone.get(zone, ()) if zone else self.model.files
        selected = sorted(values, key=lambda item: (-item.lines, -item.size, item.path))[:limit]
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "largest-files")

    def entrypoints(self, *, limit: int = 100) -> QueryResult:
        paths = {path for subsystem in self.model.subsystems for path in subsystem.entrypoints}
        selected = [item for item in self.model.files if item.path in paths][:limit]
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "entrypoints")

    def tests_for_zone(self, zone: str, *, limit: int = 200) -> QueryResult:
        direct = [item for item in self._by_zone.get(zone, ()) if item.kind == "test"]
        shared = [item for item in self._by_zone.get("tests", ()) if item.kind == "test"]
        selected = sorted({item.path: item for item in direct + shared}.values(), key=lambda item: item.path)[:limit]
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "zone-tests")

    def dependency_closure(self, zones: Iterable[str], *, depth: int = 2) -> tuple[str, ...]:
        if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 16:
            raise ValueError("depth must be in [0,16]")
        seen = {str(zone) for zone in zones if str(zone)}
        frontier = deque((zone, 0) for zone in sorted(seen))
        while frontier:
            zone, level = frontier.popleft()
            if level >= depth:
                continue
            for dependency in self._dependencies.get(zone, ()):
                if dependency not in seen:
                    seen.add(dependency)
                    frontier.append((dependency, level + 1))
        return tuple(sorted(seen))

    def dependent_closure(self, zones: Iterable[str], *, depth: int = 2) -> tuple[str, ...]:
        if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 16:
            raise ValueError("depth must be in [0,16]")
        seen = {str(zone) for zone in zones if str(zone)}
        frontier = deque((zone, 0) for zone in sorted(seen))
        while frontier:
            zone, level = frontier.popleft()
            if level >= depth:
                continue
            for dependent in self._dependents.get(zone, ()):
                if dependent not in seen:
                    seen.add(dependent)
                    frontier.append((dependent, level + 1))
        return tuple(sorted(seen))

    def verification_files(
        self,
        zones: Iterable[str],
        *,
        depth: int = 2,
        limit: int = 200,
    ) -> QueryResult:
        impacted = self.dependent_closure(zones, depth=depth)
        tests: dict[str, FileRecord] = {}
        for zone in impacted:
            for item in self._by_zone.get(zone, ()):
                if item.kind == "test":
                    tests[item.path] = item
        for item in self._by_kind.get("test", ()):
            if item.zone == "tests":
                tests[item.path] = item
        selected = tuple(sorted(tests.values(), key=lambda item: (item.zone, item.path))[:limit])
        return QueryResult(selected, tuple(sorted({item.zone for item in selected})), "dependency-aware-verification")
