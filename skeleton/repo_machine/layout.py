"""Repository layout profile and top-level organization analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class RootSurface:
    name: str
    files: int
    source_files: int
    test_files: int
    docs: int
    zones: tuple[str, ...]
    total_lines: int

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "files": self.files,
            "source_files": self.source_files,
            "test_files": self.test_files,
            "docs": self.docs,
            "zones": list(self.zones),
            "total_lines": self.total_lines,
        }


@dataclass(frozen=True, slots=True)
class LayoutProfile:
    roots: tuple[RootSurface, ...]
    root_file_count: int
    root_directory_count: int
    mixed_zone_roots: tuple[str, ...]
    source_heavy_roots: tuple[str, ...]
    recommendations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "roots": [item.as_dict() for item in self.roots],
            "root_file_count": self.root_file_count,
            "root_directory_count": self.root_directory_count,
            "mixed_zone_roots": list(self.mixed_zone_roots),
            "source_heavy_roots": list(self.source_heavy_roots),
            "recommendations": list(self.recommendations),
        }


def analyze_layout(model: RepositoryModel) -> LayoutProfile:
    grouped: dict[str, list] = {}
    root_files = 0
    for record in model.files:
        parts = PurePosixPath(record.path).parts
        if len(parts) == 1:
            root_files += 1
            root = "<root>"
        else:
            root = parts[0]
        grouped.setdefault(root, []).append(record)

    surfaces: list[RootSurface] = []
    mixed: list[str] = []
    source_heavy: list[str] = []
    recommendations: list[str] = []
    for root, records in sorted(grouped.items()):
        zones = tuple(sorted({item.zone for item in records}))
        surface = RootSurface(
            name=root,
            files=len(records),
            source_files=sum(item.kind == "source" for item in records),
            test_files=sum(item.kind == "test" for item in records),
            docs=sum(item.kind == "docs" for item in records),
            zones=zones,
            total_lines=sum(item.lines for item in records),
        )
        surfaces.append(surface)
        if len(zones) >= 4:
            mixed.append(root)
        if surface.source_files >= 50 and surface.test_files == 0:
            source_heavy.append(root)

    if root_files >= 50:
        recommendations.append(
            "reduce top-level file fanout by grouping cohesive machine-owned surfaces"
        )
    if mixed:
        recommendations.append(
            "split or explicitly document top-level roots spanning many machine zones"
        )
    if source_heavy:
        recommendations.append(
            "co-locate or clearly map tests for large source-heavy roots"
        )
    if len(grouped) >= 40:
        recommendations.append(
            "reduce top-level directory fanout or add canonical navigation groupings"
        )

    return LayoutProfile(
        roots=tuple(surfaces),
        root_file_count=root_files,
        root_directory_count=sum(name != "<root>" for name in grouped),
        mixed_zone_roots=tuple(mixed),
        source_heavy_roots=tuple(source_heavy),
        recommendations=tuple(recommendations),
    )
