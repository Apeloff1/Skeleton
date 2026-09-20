"""Canonical data contracts for machine-readable repository organization."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Iterable, Mapping

_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,191}$")
_ZONE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_CRITICALITY = {"low", "medium", "high", "critical"}
_ALLOWED_SEVERITY = {"info", "low", "medium", "high", "critical"}
_ALLOWED_KINDS = {
    "source", "test", "workflow", "config", "docs", "script",
    "data", "generated", "unknown",
}


def _text(name: str, value: object, maximum: int = 512, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    value = value.strip()
    if not value and not empty:
        raise ValueError(f"{name} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds maximum length")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise ValueError(f"{name} contains control characters")
    return value


def _token(name: str, value: object) -> str:
    value = _text(name, value, 192).casefold()
    if _TOKEN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical token")
    return value


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ZoneRule:
    name: str
    prefixes: tuple[str, ...]
    owner: str
    criticality: str = "medium"

    def __post_init__(self) -> None:
        zone_name = _token("zone name", self.name)
        if _ZONE_TOKEN.fullmatch(zone_name) is None:
            raise ValueError(
                "zone name must be a filename-safe canonical token"
            )
        object.__setattr__(self, "name", zone_name)
        object.__setattr__(self, "owner", _token("zone owner", self.owner))
        criticality = _text("criticality", self.criticality, 16).casefold()
        if criticality not in _ALLOWED_CRITICALITY:
            raise ValueError("invalid zone criticality")
        object.__setattr__(self, "criticality", criticality)
        prefixes = tuple(sorted({_text("prefix", item, 256) for item in self.prefixes}))
        if not prefixes:
            raise ValueError("zone requires at least one prefix")
        object.__setattr__(self, "prefixes", prefixes)

    def matches(self, path: str) -> bool:
        return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in self.prefixes)


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    zone: str
    owner: str
    kind: str
    language: str
    size: int
    lines: int
    sha256: str
    symbols: int = 0
    imports: tuple[str, ...] = ()
    test_target: str | None = None

    def __post_init__(self) -> None:
        _text("path", self.path, 1024)
        _token("zone", self.zone)
        _token("owner", self.owner)
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError("invalid file kind")
        _token("language", self.language)
        for name in ("size", "lines", "symbols"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("sha256 must be canonical lowercase hex")

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "zone": self.zone,
            "owner": self.owner,
            "kind": self.kind,
            "language": self.language,
            "size": self.size,
            "lines": self.lines,
            "sha256": self.sha256,
            "symbols": self.symbols,
            "imports": list(self.imports),
            "test_target": self.test_target,
        }


@dataclass(frozen=True, slots=True)
class TopologyEdge:
    source: str
    target: str
    kind: str
    evidence_count: int = 1

    def __post_init__(self) -> None:
        _token("edge source", self.source)
        _token("edge target", self.target)
        _token("edge kind", self.kind)
        if isinstance(self.evidence_count, bool) or not isinstance(self.evidence_count, int) or self.evidence_count < 1:
            raise ValueError("edge evidence_count must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "evidence_count": self.evidence_count,
        }


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    zone: str
    path: str = ""
    detail: str = ""
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _token("finding code", self.code)
        sev = _text("severity", self.severity, 16).casefold()
        if sev not in _ALLOWED_SEVERITY:
            raise ValueError("invalid finding severity")
        object.__setattr__(self, "severity", sev)
        _token("finding zone", self.zone)
        if self.path:
            _text("finding path", self.path, 1024)
        if self.detail:
            _text("finding detail", self.detail, 2048)
        object.__setattr__(
            self,
            "evidence",
            tuple(sorted({_text("finding evidence", item, 1024) for item in self.evidence})),
        )

    @property
    def identity(self) -> str:
        return digest([self.code, self.zone, self.path, self.detail])[:24]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.identity,
            "code": self.code,
            "severity": self.severity,
            "zone": self.zone,
            "path": self.path,
            "detail": self.detail,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class SubsystemRecord:
    name: str
    owner: str
    criticality: str
    file_count: int
    code_files: int
    test_files: int
    workflow_files: int
    total_lines: int
    total_bytes: int
    languages: tuple[str, ...] = ()
    entrypoints: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "owner": self.owner,
            "criticality": self.criticality,
            "file_count": self.file_count,
            "code_files": self.code_files,
            "test_files": self.test_files,
            "workflow_files": self.workflow_files,
            "total_lines": self.total_lines,
            "total_bytes": self.total_bytes,
            "languages": list(self.languages),
            "entrypoints": list(self.entrypoints),
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
        }


@dataclass(frozen=True, slots=True)
class RepositoryModel:
    schema_version: int
    repository: str
    files: tuple[FileRecord, ...]
    subsystems: tuple[SubsystemRecord, ...]
    edges: tuple[TopologyEdge, ...]
    findings: tuple[Finding, ...]
    cycles: tuple[tuple[str, ...], ...] = ()
    unclassified_count: int = 0
    truncated: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return digest(self.as_dict(include_files=False))

    def as_dict(self, *, include_files: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "subsystems": [item.as_dict() for item in self.subsystems],
            "edges": [item.as_dict() for item in self.edges],
            "findings": [item.as_dict() for item in self.findings],
            "cycles": [list(item) for item in self.cycles],
            "unclassified_count": self.unclassified_count,
            "truncated": self.truncated,
            "metadata": dict(self.metadata),
        }
        if include_files:
            payload["files"] = [item.as_dict() for item in self.files]
        return payload

    def machine_context(self, *, max_findings: int = 40) -> dict[str, object]:
        rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        findings = sorted(
            self.findings,
            key=lambda item: (-rank[item.severity], item.zone, item.code, item.path),
        )[:max_findings]
        return {
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint,
            "repository": self.repository,
            "subsystems": [item.as_dict() for item in self.subsystems],
            "topology": {
                "edges": [item.as_dict() for item in self.edges],
                "cycles": [list(item) for item in self.cycles],
            },
            "organization_findings": [item.as_dict() for item in findings],
            "unclassified_count": self.unclassified_count,
            "truncated": self.truncated,
        }


def unique_findings(items: Iterable[Finding]) -> tuple[Finding, ...]:
    found: dict[str, Finding] = {}
    for item in items:
        found.setdefault(item.identity, item)
    return tuple(sorted(found.values(), key=lambda x: (x.zone, x.code, x.path, x.identity)))
