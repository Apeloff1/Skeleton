"""Machine catalog of repository capabilities, entrypoints, workflows and tests."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    identity: str
    zone: str
    kind: str
    path: str
    language: str
    owner: str
    related_tests: tuple[str, ...]
    dependencies: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "zone": self.zone,
            "kind": self.kind,
            "path": self.path,
            "language": self.language,
            "owner": self.owner,
            "related_tests": list(self.related_tests),
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class RepositoryCatalog:
    capabilities: tuple[CapabilityRecord, ...]
    _by_zone: dict[str, tuple[CapabilityRecord, ...]] | None = None

    def as_dict(self) -> dict[str, object]:
        return {"capabilities": [item.as_dict() for item in self.capabilities]}

    def by_zone(self, zone: str) -> tuple[CapabilityRecord, ...]:
        if self._by_zone is None:
            return tuple(item for item in self.capabilities if item.zone == zone)
        return self._by_zone.get(zone, ())

    def workflows(self) -> tuple[CapabilityRecord, ...]:
        return tuple(item for item in self.capabilities if item.kind == "workflow")

    def entrypoints(self) -> tuple[CapabilityRecord, ...]:
        return tuple(item for item in self.capabilities if item.kind == "entrypoint")


def _identity(zone: str, kind: str, path: str) -> str:
    normalized = path.replace("/", ":").replace(".", "-").strip("-:")
    return f"{zone}:{kind}:{normalized}"[:240]


def build_catalog(model: RepositoryModel) -> RepositoryCatalog:
    subsystem_by_name = {item.name: item for item in model.subsystems}
    entrypoints = {
        path
        for subsystem in model.subsystems
        for path in subsystem.entrypoints
    }
    tests_by_zone: dict[str, list[object]] = {}
    test_stems: dict[str, list[object]] = {}
    for test in model.files:
        if test.kind != "test":
            continue
        tests_by_zone.setdefault(test.zone, []).append(test)
        stem = PurePosixPath(test.path).stem.casefold()
        if stem:
            test_stems.setdefault(stem, []).append(test)

    # Cache the existing substring semantics per capability stem. A large
    # repository often has many capabilities sharing the same basename.
    stem_matches: dict[str, tuple[object, ...]] = {}

    capabilities: list[CapabilityRecord] = []
    for item in model.files:
        kind = ""
        if item.kind == "workflow":
            kind = "workflow"
        elif item.path in entrypoints:
            kind = "entrypoint"
        elif item.kind == "source":
            kind = "module"
        elif item.kind == "config" and PurePosixPath(item.path).name in {
            "pyproject.toml", "package.json", "docker-compose.yml",
            "docker-compose.yaml", "settings.py",
        }:
            kind = "configuration"
        if not kind:
            continue

        stem = PurePosixPath(item.path).stem.casefold()
        related_paths = {test.path for test in tests_by_zone.get(item.zone, ())}
        if stem:
            matches = stem_matches.get(stem)
            if matches is None:
                matches = tuple(
                    test
                    for test_stem, tests in test_stems.items()
                    if stem in test_stem
                    for test in tests
                )
                stem_matches[stem] = matches
            related_paths.update(test.path for test in matches)
        related = tuple(sorted(related_paths)[:32])
        subsystem = subsystem_by_name.get(item.zone)
        dependencies = subsystem.dependencies if subsystem else ()
        capabilities.append(CapabilityRecord(
            identity=_identity(item.zone, kind, item.path),
            zone=item.zone,
            kind=kind,
            path=item.path,
            language=item.language,
            owner=item.owner,
            related_tests=related,
            dependencies=dependencies,
        ))

    ordered = tuple(sorted(
        capabilities,
        key=lambda item: (item.zone, item.kind, item.path),
    ))
    by_zone: dict[str, list[CapabilityRecord]] = {}
    for item in ordered:
        by_zone.setdefault(item.zone, []).append(item)
    return RepositoryCatalog(
        ordered,
        {zone: tuple(items) for zone, items in by_zone.items()},
    )
