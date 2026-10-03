"""Compact navigation index optimized for agent path discovery."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable

from .model import FileRecord, RepositoryModel


@dataclass(slots=True)
class _Node:
    name: str
    files: int = 0
    source: int = 0
    tests: int = 0
    children: dict[str, "_Node"] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NavigationEntry:
    prefix: str
    files: int
    source_files: int
    test_files: int
    child_names: tuple[str, ...]
    zones: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "prefix": self.prefix,
            "files": self.files,
            "source_files": self.source_files,
            "test_files": self.test_files,
            "child_names": list(self.child_names),
            "zones": list(self.zones),
        }


class NavigationIndex:
    def __init__(self, model: RepositoryModel) -> None:
        self.model = model
        self._root = _Node("")
        self._paths = {item.path: item for item in model.files}
        self._zones_by_prefix = {}
        self._files_by_zone: dict[str, tuple[FileRecord, ...]] = {}
        self._files_by_kind: dict[str, tuple[FileRecord, ...]] = {}
        self._build()

    def _build(self) -> None:
        by_zone: dict[str, list[FileRecord]] = {}
        for record in self.model.files:
            by_zone.setdefault(record.zone, []).append(record)
            node = self._root
            node.files += 1
            node.source += int(record.kind == "source")
            node.tests += int(record.kind == "test")
            prefix = ""
            for part in PurePosixPath(record.path).parts[:-1]:
                prefix = f"{prefix}/{part}".strip("/")
                self._zones_by_prefix.setdefault(prefix, set()).add(record.zone)
                node = node.children.setdefault(part, _Node(part))
                node.files += 1
                node.source += int(record.kind == "source")
                node.tests += int(record.kind == "test")
        self._files_by_zone = {
            zone: tuple(sorted(records, key=lambda item: item.path))
            for zone, records in by_zone.items()
        }
        by_kind: dict[str, list[FileRecord]] = {}
        for record in self.model.files:
            by_kind.setdefault(record.kind.casefold(), []).append(record)
        self._files_by_kind = {
            kind: tuple(sorted(records, key=lambda item: item.path))
            for kind, records in by_kind.items()
        }

    def directory(self, prefix: str = "") -> NavigationEntry:
        normalized = prefix.strip("/")
        node = self._root
        if normalized:
            for part in PurePosixPath(normalized).parts:
                if part not in node.children:
                    return NavigationEntry(normalized, 0, 0, 0, (), ())
                node = node.children[part]
        path_prefix = normalized + "/" if normalized else ""
        zones = tuple(sorted(self._zones_by_prefix.get(normalized, set())))
        return NavigationEntry(
            prefix=normalized,
            files=node.files,
            source_files=node.source,
            test_files=node.tests,
            child_names=tuple(sorted(node.children)),
            zones=zones,
        )

    def nearest(
        self,
        *,
        zone: str = "",
        name_contains: str = "",
        kinds: Iterable[str] = (),
        limit: int = 50,
    ) -> tuple[FileRecord, ...]:
        needle = name_contains.casefold().strip()
        kind_set = {item.casefold() for item in kinds}
        values: list[FileRecord] = []
        if zone:
            records = self._files_by_zone.get(zone, ())
        elif len(kind_set) == 1:
            records = self._files_by_kind.get(next(iter(kind_set)), ())
        else:
            records = self.model.files
        for record in records:
            if zone and record.zone != zone:
                continue
            if needle and needle not in record.path.casefold():
                continue
            if kind_set and record.kind.casefold() not in kind_set:
                continue
            values.append(record)
        values.sort(key=lambda item: (
            0 if needle and PurePosixPath(item.path).stem.casefold() == needle else 1,
            len(PurePosixPath(item.path).parts),
            item.path,
        ))
        return tuple(values[:limit])
