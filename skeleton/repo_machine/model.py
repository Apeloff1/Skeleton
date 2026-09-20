"""Typed repository-machine domain model.

The machine plane intentionally depends only on the Python standard library.
Its objects are immutable, JSON-safe at the boundary, and reject ambiguous
metadata early.  They are used by scanners, graph builders, work planners,
contract gates, and autonomous agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


class MachineModelError(ValueError):
    """Machine metadata is malformed or violates a closed-world invariant."""


class ZoneKind(str, Enum):
    CONTROL = "control"
    PRODUCT = "product"
    TEST = "test"
    DOCS = "docs"
    DATA = "data"
    ARCHIVE = "archive"
    METADATA = "metadata"
    UNKNOWN = "unknown"


class Mutability(str, Enum):
    NORMAL = "normal"
    GUARDED = "guarded"
    GENERATED = "generated"
    ARCHIVE = "archive"
    IMMUTABLE = "immutable"


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Lifecycle(str, Enum):
    ACTIVE = "active"
    DATA = "data"
    ARCHIVE = "archive"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"


class FileRole(str, Enum):
    SOURCE = "source"
    TEST = "test"
    DOC = "doc"
    CONFIG = "config"
    WORKFLOW = "workflow"
    SCRIPT = "script"
    DATA = "data"
    ASSET = "asset"
    GENERATED = "generated"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


class EdgeKind(str, Enum):
    IMPORT = "import"
    SUBSYSTEM = "subsystem"
    TESTS = "tests"
    DOCUMENTS = "documents"
    OWNS = "owns"
    CONFIGURES = "configures"
    TRIGGERS = "triggers"


def _clean_id(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise MachineModelError(f"{label} must be text")
    clean = value.strip()
    if not clean:
        raise MachineModelError(f"{label} must not be empty")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.:")
    if any(char.casefold() not in allowed for char in clean):
        raise MachineModelError(f"{label} contains unsupported characters")
    return clean


def _path(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise MachineModelError(f"{label} must be text")
    raw = value.replace("\\", "/").strip("/")
    if not raw:
        raise MachineModelError(f"{label} must not be empty")
    parsed = PurePosixPath(raw)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise MachineModelError(f"{label} is not a safe repository path")
    return parsed.as_posix()


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise MachineModelError(f"{label} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise MachineModelError(f"{label} entries must be non-empty text")
        result.append(item.strip())
    return tuple(dict.fromkeys(result))


@dataclass(frozen=True, slots=True)
class Zone:
    id: str
    description: str
    roots: tuple[str, ...] = ()
    exact_paths: tuple[str, ...] = ()
    exclude_roots: tuple[str, ...] = ()
    kind: ZoneKind = ZoneKind.UNKNOWN
    mutability: Mutability = Mutability.GUARDED
    risk: Risk = Risk.MEDIUM
    agent_default: str = "inspect"
    allowed_actions: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _clean_id(self.id, label="zone id"))
        if not self.description.strip():
            raise MachineModelError("zone description must not be empty")
        roots = tuple(_path(item, label="zone root") for item in self.roots)
        exact = tuple(_path(item, label="zone exact path") for item in self.exact_paths)
        excluded = tuple(_path(item, label="zone excluded root") for item in self.exclude_roots)
        if not roots and not exact:
            raise MachineModelError(f"zone {self.id!r} has no roots or exact paths")
        object.__setattr__(self, "roots", roots)
        object.__setattr__(self, "exact_paths", exact)
        object.__setattr__(self, "exclude_roots", excluded)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Zone":
        try:
            return cls(
                id=value["id"],
                description=str(value.get("description", "")),
                roots=_string_tuple(value.get("roots"), label="zone roots"),
                exact_paths=_string_tuple(value.get("exact_paths"), label="zone exact paths"),
                exclude_roots=_string_tuple(value.get("exclude_roots"), label="zone exclusions"),
                kind=ZoneKind(str(value.get("kind", "unknown"))),
                mutability=Mutability(str(value.get("mutability", "guarded"))),
                risk=Risk(str(value.get("risk", "medium"))),
                agent_default=str(value.get("agent_default", "inspect")),
                allowed_actions=_string_tuple(value.get("allowed_actions"), label="zone actions"),
                required_evidence=_string_tuple(value.get("required_evidence"), label="zone evidence"),
                tags=_string_tuple(value.get("tags"), label="zone tags"),
            )
        except (KeyError, ValueError) as exc:
            raise MachineModelError(f"invalid zone: {exc}") from exc

    def matches(self, path: str) -> bool:
        candidate = _path(path, label="candidate path")
        if candidate in self.exact_paths:
            return True
        if any(candidate == excluded or candidate.startswith(excluded + "/") for excluded in self.exclude_roots):
            return False
        return any(candidate == root or candidate.startswith(root + "/") for root in self.roots)

    @property
    def specificity(self) -> int:
        candidates = [len(PurePosixPath(item).parts) for item in (*self.roots, *self.exact_paths)]
        return max(candidates, default=0)


@dataclass(frozen=True, slots=True)
class Subsystem:
    id: str
    name: str
    roots: tuple[str, ...]
    owner: str
    criticality: Risk
    lifecycle: Lifecycle
    tags: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    test_roots: tuple[str, ...] = ()
    doc_roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _clean_id(self.id, label="subsystem id"))
        if not self.name.strip():
            raise MachineModelError("subsystem name must not be empty")
        object.__setattr__(self, "roots", tuple(_path(item, label="subsystem root") for item in self.roots))
        if not self.roots:
            raise MachineModelError(f"subsystem {self.id!r} has no roots")
        object.__setattr__(self, "owner", _clean_id(self.owner, label="subsystem owner"))
        object.__setattr__(self, "test_roots", tuple(_path(item, label="test root") for item in self.test_roots))
        object.__setattr__(self, "doc_roots", tuple(_path(item, label="doc root") for item in self.doc_roots))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Subsystem":
        try:
            return cls(
                id=value["id"],
                name=str(value.get("name", "")),
                roots=_string_tuple(value.get("roots"), label="subsystem roots"),
                owner=value.get("owner", "machine:unowned"),
                criticality=Risk(str(value.get("criticality", "medium"))),
                lifecycle=Lifecycle(str(value.get("lifecycle", "active"))),
                tags=_string_tuple(value.get("tags"), label="subsystem tags"),
                depends_on=_string_tuple(value.get("depends_on"), label="subsystem dependencies"),
                test_roots=_string_tuple(value.get("test_roots"), label="subsystem test roots"),
                doc_roots=_string_tuple(value.get("doc_roots"), label="subsystem doc roots"),
            )
        except (KeyError, ValueError) as exc:
            raise MachineModelError(f"invalid subsystem: {exc}") from exc

    def matches(self, path: str) -> bool:
        candidate = _path(path, label="candidate path")
        return any(candidate == root or candidate.startswith(root + "/") for root in self.roots)

    @property
    def specificity(self) -> int:
        return max((len(PurePosixPath(root).parts) for root in self.roots), default=0)


@dataclass(frozen=True, slots=True)
class ImportRef:
    module: str
    line: int
    kind: str = "import"
    names: tuple[str, ...] = ()
    level: int = 0

    def __post_init__(self) -> None:
        if not self.module and self.level == 0:
            raise MachineModelError("absolute import must name a module")
        if isinstance(self.line, bool) or self.line < 1:
            raise MachineModelError("import line must be positive")


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    kind: str
    line: int
    exported: bool = False
    decorators: tuple[str, ...] = ()
    bases: tuple[str, ...] = ()
    async_def: bool = False


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    zone_id: str
    subsystem_id: str | None
    role: FileRole
    suffix: str
    language: str
    size_bytes: int
    lines: int | None
    digest: str | None
    generated: bool
    binary: bool
    imports: tuple[ImportRef, ...] = ()
    symbols: tuple[Symbol, ...] = ()
    todos: tuple[str, ...] = ()
    parse_error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path, label="file path"))
        if self.size_bytes < 0:
            raise MachineModelError("file size must be non-negative")
        if self.lines is not None and self.lines < 0:
            raise MachineModelError("line count must be non-negative")
        if self.digest is not None:
            digest = self.digest.casefold()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise MachineModelError("file digest must be sha256 hex")
            object.__setattr__(self, "digest", digest)

    @property
    def active(self) -> bool:
        return self.role not in {FileRole.ARCHIVE, FileRole.GENERATED}

    @property
    def module_name(self) -> str | None:
        if self.suffix not in {".py", ".pyi"}:
            return None
        parts = list(PurePosixPath(self.path).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts) if parts else None


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source: str
    target: str
    kind: EdgeKind
    detail: str = ""
    line: int | None = None
    external: bool = False

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise MachineModelError("dependency edge endpoints must not be empty")


@dataclass(frozen=True, slots=True)
class SubsystemStats:
    subsystem_id: str
    files: int = 0
    source_files: int = 0
    test_files: int = 0
    docs_files: int = 0
    lines: int = 0
    bytes: int = 0
    imports_out: int = 0
    imports_in: int = 0
    parse_errors: int = 0
    todos: int = 0
    orphan_files: int = 0


@dataclass(frozen=True, slots=True)
class WorkCandidate:
    id: str
    lane: str
    title: str
    rationale: str
    score: float
    subsystem_id: str | None
    paths: tuple[str, ...]
    evidence: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    recommended_tests: tuple[str, ...] = ()
    mutations_allowed: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _clean_id(self.id, label="work candidate id"))
        if not 0.0 <= self.score <= 1.0:
            raise MachineModelError("work candidate score must be within [0,1]")
        if not self.title.strip() or not self.rationale.strip():
            raise MachineModelError("work candidate title and rationale are required")
        object.__setattr__(self, "paths", tuple(_path(item, label="candidate path") for item in self.paths))


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    schema_version: int
    repository: str
    head: str | None
    files: tuple[FileRecord, ...]
    edges: tuple[DependencyEdge, ...]
    subsystems: tuple[Subsystem, ...]
    zones: tuple[Zone, ...]
    work_candidates: tuple[WorkCandidate, ...] = ()
    findings: tuple[str, ...] = ()

    def file_map(self) -> dict[str, FileRecord]:
        return {item.path: item for item in self.files}

    def subsystem_map(self) -> dict[str, Subsystem]:
        return {item.id: item for item in self.subsystems}

    def zone_map(self) -> dict[str, Zone]:
        return {item.id: item for item in self.zones}

    def files_for_subsystem(self, subsystem_id: str) -> tuple[FileRecord, ...]:
        return tuple(item for item in self.files if item.subsystem_id == subsystem_id)

    def files_for_zone(self, zone_id: str) -> tuple[FileRecord, ...]:
        return tuple(item for item in self.files if item.zone_id == zone_id)


def ensure_unique_ids(items: Iterable[Any], *, label: str) -> None:
    seen: set[str] = set()
    for item in items:
        identifier = getattr(item, "id", None)
        if not isinstance(identifier, str):
            raise MachineModelError(f"{label} entry is missing id")
        if identifier in seen:
            raise MachineModelError(f"duplicate {label} id: {identifier}")
        seen.add(identifier)


def validate_subsystem_graph(subsystems: Sequence[Subsystem]) -> None:
    ensure_unique_ids(subsystems, label="subsystem")
    known = {item.id for item in subsystems}
    for subsystem in subsystems:
        missing = set(subsystem.depends_on) - known
        if missing:
            raise MachineModelError(
                f"subsystem {subsystem.id!r} depends on unknown ids: {sorted(missing)}"
            )
        if subsystem.id in subsystem.depends_on:
            raise MachineModelError(f"subsystem {subsystem.id!r} depends on itself")


def as_primitive(value: Any) -> Any:
    """Convert model objects to stable JSON-compatible primitives."""
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: as_primitive(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, Mapping):
        return {str(key): as_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [as_primitive(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported primitive conversion: {type(value).__name__}")
