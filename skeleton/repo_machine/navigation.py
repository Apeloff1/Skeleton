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
        self._build()

    def _build(self) -> None:
        for record in self.model.files:
            node = self._root
            node.files += 1
            node.source += int(record.kind == "source")
            node.tests += int(record.kind == "test")
            for part in PurePosixPath(record.path).parts[:-1]:
                node = node.children.setdefault(part, _Node(part))
                node.files += 1
                node.source += int(record.kind == "source")
                node.tests += int(record.kind == "test")

    def directory(self, prefix: str = "") -> NavigationEntry:
        normalized = prefix.strip("/")
        node = self._root
        if normalized:
            for part in PurePosixPath(normalized).parts:
                if part not in node.children:
                    return NavigationEntry(normalized, 0, 0, 0, (), ())
                node = node.children[part]
        path_prefix = normalized + "/" if normalized else ""
        zones = tuple(sorted({
            record.zone
            for path, record in self._paths.items()
            if path.startswith(path_prefix)
        }))
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
        for record in self.model.files:
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
