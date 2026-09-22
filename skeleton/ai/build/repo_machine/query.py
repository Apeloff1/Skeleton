"""Fast deterministic queries over RepositoryModel for agents and tooling."""
from __future__ import annotations

from collections import defaultdict
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
        self._by_zone: dict[str, list[FileRecord]] = defaultdict(list)
        for item in model.files:
            self._by_zone[item.zone].append(item)

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
        selected: list[FileRecord] = []
        for item in self.model.files:
            if zone_set and item.zone.casefold() not in zone_set:
                continue
            if kind_set and item.kind.casefold() not in kind_set:
                continue
            if language_set and item.language.casefold() not in language_set:
                continue
            if globs and not any(fnmatch(item.path, pattern) for pattern in globs):
                continue
            selected.append(item)
            if len(selected) >= limit:
                break
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "deterministic-filter")

    def largest_files(self, *, zone: str = "", limit: int = 25) -> QueryResult:
        values = self._by_zone.get(zone, []) if zone else list(self.model.files)
        selected = sorted(values, key=lambda item: (-item.lines, -item.size, item.path))[:limit]
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "largest-files")

    def entrypoints(self, *, limit: int = 100) -> QueryResult:
        paths = {path for subsystem in self.model.subsystems for path in subsystem.entrypoints}
        selected = [item for item in self.model.files if item.path in paths][:limit]
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "entrypoints")

    def tests_for_zone(self, zone: str, *, limit: int = 200) -> QueryResult:
        direct = [item for item in self._by_zone.get(zone, []) if item.kind == "test"]
        shared = [item for item in self._by_zone.get("tests", []) if item.kind == "test"]
        selected = sorted({item.path: item for item in direct + shared}.values(), key=lambda item: item.path)[:limit]
        return QueryResult(tuple(selected), tuple(sorted({item.zone for item in selected})), "zone-tests")
