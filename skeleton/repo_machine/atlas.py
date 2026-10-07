"""Deterministic human/machine repository information architecture.

The atlas is derived from the live repository model plus the canonical
.machine/repository.toml zone policy. It is metadata-only and never imports,
executes, moves, or rewrites repository content.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .config import MachineConfig
from .model import RepositoryModel, ZoneRule


@dataclass(frozen=True, slots=True)
class PathPlacement:
    path: str
    zone: str
    owner: str
    criticality: str
    audience: str
    lifecycle: str
    purpose: str
    matched_prefix: str

    def as_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "zone": self.zone,
            "owner": self.owner,
            "criticality": self.criticality,
            "audience": self.audience,
            "lifecycle": self.lifecycle,
            "purpose": self.purpose,
            "matched_prefix": self.matched_prefix,
        }


@dataclass(frozen=True, slots=True)
class AtlasZone:
    name: str
    owner: str
    criticality: str
    audience: str
    lifecycle: str
    purpose: str
    prefixes: tuple[str, ...]
    file_count: int
    code_files: int
    test_files: int
    workflow_files: int
    total_lines: int
    dependencies: tuple[str, ...]
    dependents: tuple[str, ...]
    referenced_test_files: int = 0
    test_evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "owner": self.owner,
            "criticality": self.criticality,
            "audience": self.audience,
            "lifecycle": self.lifecycle,
            "purpose": self.purpose,
            "prefixes": list(self.prefixes),
            "file_count": self.file_count,
            "code_files": self.code_files,
            "test_files": self.test_files,
            "referenced_test_files": self.referenced_test_files,
            "test_evidence": list(self.test_evidence),
            "workflow_files": self.workflow_files,
            "total_lines": self.total_lines,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
        }


@dataclass(frozen=True, slots=True)
class RepositoryAtlas:
    schema_version: int
    repository: str
    repository_fingerprint: str
    contract: str
    zones: tuple[AtlasZone, ...]
    unclassified_count: int
    unclassified_roots: tuple[str, ...]
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "repository_fingerprint": self.repository_fingerprint,
            "contract": self.contract,
            "classification": {
                "first_match_wins": True,
                "fallback_zone": "unclassified",
                "unclassified_count": self.unclassified_count,
                "unclassified_roots": list(self.unclassified_roots),
                "truncated": self.truncated,
            },
            "zones": [item.as_dict() for item in self.zones],
        }


def _canonical_path(path: str) -> str:
    if not isinstance(path, str):
        raise TypeError("path must be text")
    normalized = path.replace("\\", "/")
    if not normalized or normalized != normalized.strip("/"):
        raise ValueError("path must be canonical and repository-relative")
    path = normalized
    posix = PurePosixPath(path)
    if (
        posix.is_absolute()
        or any(part in {"", ".", ".."} for part in posix.parts)
        or posix.as_posix() != path
    ):
        raise ValueError("path must be canonical and repository-relative")
    return path


def placement_for_path(config: MachineConfig, path: str) -> PathPlacement:
    normalized = _canonical_path(path)
    for rule in config.zones:
        if not rule.matches(normalized):
            continue
        matches = tuple(
            prefix
            for prefix in rule.prefixes
            if normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        )
        matched = max(matches, key=len)
        return PathPlacement(
            path=normalized,
            zone=rule.name,
            owner=rule.owner,
            criticality=rule.criticality,
            audience=rule.audience,
            lifecycle=rule.lifecycle,
            purpose=rule.purpose,
            matched_prefix=matched,
        )
    return PathPlacement(
        path=normalized,
        zone="unclassified",
        owner=config.default_owner,
        criticality="medium",
        audience="internal",
        lifecycle="transitional",
        purpose="Path is not covered by the canonical repository taxonomy.",
        matched_prefix="",
    )


def _atlas_zone(rule: ZoneRule, subsystem: object | None) -> AtlasZone:
    if subsystem is None:
        return AtlasZone(
            name=rule.name,
            owner=rule.owner,
            criticality=rule.criticality,
            audience=rule.audience,
            lifecycle=rule.lifecycle,
            purpose=rule.purpose,
            prefixes=rule.prefixes,
            file_count=0,
            code_files=0,
            test_files=0,
            workflow_files=0,
            total_lines=0,
            dependencies=(),
            dependents=(),
        )
    return AtlasZone(
        name=rule.name,
        owner=rule.owner,
        criticality=rule.criticality,
        audience=rule.audience,
        lifecycle=rule.lifecycle,
        purpose=rule.purpose,
        prefixes=rule.prefixes,
        file_count=subsystem.file_count,
        code_files=subsystem.code_files,
        test_files=subsystem.test_files,
        referenced_test_files=subsystem.referenced_test_files,
        test_evidence=subsystem.test_evidence,
        workflow_files=subsystem.workflow_files,
        total_lines=subsystem.total_lines,
        dependencies=subsystem.dependencies,
        dependents=subsystem.dependents,
    )


def build_repository_atlas(
    model: RepositoryModel,
    config: MachineConfig,
) -> RepositoryAtlas:
    by_name = {item.name: item for item in model.subsystems}
    roots = tuple(sorted({
        PurePosixPath(record.path).parts[0]
        for record in model.files
        if record.zone == "unclassified" and PurePosixPath(record.path).parts
    }))
    return RepositoryAtlas(
        schema_version=1,
        repository=model.repository,
        repository_fingerprint=model.fingerprint,
        contract=".machine/repository.toml",
        zones=tuple(
            _atlas_zone(rule, by_name.get(rule.name))
            for rule in config.zones
        ),
        unclassified_count=model.unclassified_count,
        unclassified_roots=roots,
        truncated=model.truncated,
    )
