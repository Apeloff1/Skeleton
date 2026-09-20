"""Repository-machine policy loading, path classification, and authority queries."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import fnmatch
import tomllib
from typing import Any, Iterable, Mapping

from .model import (
    FileRole,
    Lifecycle,
    MachineModelError,
    Mutability,
    Risk,
    Subsystem,
    Zone,
    ensure_unique_ids,
    validate_subsystem_graph,
)


LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".gd": "gdscript",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".json": "json",
    ".jsonl": "jsonl",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".graphql": "graphql",
    ".proto": "protobuf",
}


@dataclass(frozen=True, slots=True)
class ScanPolicy:
    follow_symlinks: bool
    max_file_bytes: int
    max_python_ast_bytes: int
    max_text_probe_bytes: int
    max_dependency_edges: int
    max_files: int
    hash_algorithm: str
    include_suffixes: frozenset[str]
    ignore_names: frozenset[str]
    generated_markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkPolicy:
    lane_order: tuple[str, ...]
    minimum_score: float
    max_candidates: int
    max_candidates_per_subsystem: int
    prefer_existing_pr: bool
    prefer_existing_issue: bool
    prefer_targeted_test: bool
    penalize_control_plane: float
    penalize_archive: float
    penalize_generated: float
    reward_test_gap: float
    reward_large_active_module: float
    reward_orphan_module: float
    reward_todo: float
    reward_dependency_cycle: float
    reward_high_fan_in: float
    reward_missing_docs: float


@dataclass(frozen=True, slots=True)
class RepositoryPolicy:
    root: Path
    repository: Mapping[str, Any]
    scan: ScanPolicy
    work: WorkPolicy
    raw_policy: Mapping[str, Any]
    outputs: Mapping[str, Any]
    zones: tuple[Zone, ...]
    subsystems: tuple[Subsystem, ...]

    @property
    def canonical_product_roots(self) -> tuple[str, ...]:
        return tuple(self.repository.get("canonical_product_roots", ()))

    @property
    def canonical_test_roots(self) -> tuple[str, ...]:
        return tuple(self.repository.get("canonical_test_roots", ()))

    @property
    def archive_roots(self) -> tuple[str, ...]:
        return tuple(self.repository.get("archive_roots", ()))

    @property
    def bulk_data_roots(self) -> tuple[str, ...]:
        return tuple(self.repository.get("bulk_data_roots", ()))

    def zone_for(self, path: str) -> Zone | None:
        matches = [zone for zone in self.zones if zone.matches(path)]
        if not matches:
            return None
        matches.sort(
            key=lambda item: (
                item.specificity,
                1 if path in item.exact_paths else 0,
                item.id,
            ),
            reverse=True,
        )
        return matches[0]

    def subsystem_for(self, path: str) -> Subsystem | None:
        matches = [item for item in self.subsystems if item.matches(path)]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.specificity, item.id), reverse=True)
        return matches[0]

    def role_for(self, path: str, *, generated: bool = False) -> FileRole:
        zone = self.zone_for(path)
        suffix = PurePosixPath(path).suffix.casefold()
        name = PurePosixPath(path).name.casefold()
        if zone and zone.kind.value == "archive":
            return FileRole.ARCHIVE
        if generated:
            return FileRole.GENERATED
        if zone and zone.kind.value == "test":
            return FileRole.TEST
        if zone and zone.kind.value == "docs":
            return FileRole.DOC
        if zone and zone.kind.value == "data":
            return FileRole.DATA
        if path.startswith(".github/workflows/"):
            return FileRole.WORKFLOW
        if path.startswith(("scripts/", "backend/scripts/")) or suffix in {".sh", ".bash", ".zsh"}:
            return FileRole.SCRIPT
        if suffix in {".md", ".rst"}:
            return FileRole.DOC
        if suffix in {".toml", ".yaml", ".yml", ".json"} and (
            "/" not in path or name.startswith(".")
        ):
            return FileRole.CONFIG
        if suffix in {
            ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
            ".rs", ".java", ".cs", ".gd", ".sql", ".graphql", ".proto",
        }:
            return FileRole.SOURCE
        if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp3", ".mp4", ".wav", ".ttf", ".otf"}:
            return FileRole.ASSET
        return FileRole.UNKNOWN

    def language_for(self, path: str) -> str:
        return LANGUAGES.get(PurePosixPath(path).suffix.casefold(), "unknown")

    def mutation_allowed(self, path: str, action: str) -> bool:
        zone = self.zone_for(path)
        if zone is None:
            return False
        if zone.mutability in {Mutability.ARCHIVE, Mutability.IMMUTABLE}:
            return False
        return action in zone.allowed_actions

    def risk_for(self, path: str) -> Risk:
        zone = self.zone_for(path)
        return zone.risk if zone is not None else Risk.HIGH

    def is_archive(self, path: str) -> bool:
        zone = self.zone_for(path)
        return bool(zone and zone.kind.value == "archive")

    def is_active(self, path: str) -> bool:
        return not self.is_archive(path)

    def ignored_directory(self, name: str) -> bool:
        return name in self.scan.ignore_names

    def included_suffix(self, path: str) -> bool:
        suffix = PurePosixPath(path).suffix.casefold()
        return suffix in self.scan.include_suffixes

    def recommended_tests(self, path: str) -> tuple[str, ...]:
        subsystem = self.subsystem_for(path)
        if subsystem is None:
            return ()
        return subsystem.test_roots

    def evidence_requirements(self, path: str) -> tuple[str, ...]:
        zone = self.zone_for(path)
        return zone.required_evidence if zone else ("manual-review",)


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise MachineModelError(f"{label} must be a table")
    return value


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MachineModelError(f"{label} must be a positive integer")
    return value


def _ratio(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MachineModelError(f"{label} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise MachineModelError(f"{label} must be within [0,1]")
    return result


def _bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise MachineModelError(f"{label} must be boolean")
    return value


def _load_toml(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MachineModelError(f"unable to load {path.name}: {type(exc).__name__}") from exc
    return _require_mapping(value, label=path.name)


def _scan_policy(value: Mapping[str, Any]) -> ScanPolicy:
    suffixes = value.get("include_suffixes", ())
    names = value.get("ignore_names", ())
    markers = value.get("generated_markers", ())
    if not all(isinstance(item, str) and item.startswith(".") for item in suffixes):
        raise MachineModelError("scan include_suffixes must contain suffix strings")
    if not all(isinstance(item, str) and item for item in names):
        raise MachineModelError("scan ignore_names must contain names")
    if not all(isinstance(item, str) and item for item in markers):
        raise MachineModelError("scan generated_markers must contain text")
    algorithm = value.get("hash_algorithm", "sha256")
    if algorithm != "sha256":
        raise MachineModelError("only sha256 repository digests are supported")
    return ScanPolicy(
        follow_symlinks=_bool(value.get("follow_symlinks", False), label="scan.follow_symlinks"),
        max_file_bytes=_positive_int(value.get("max_file_bytes", 1_048_576), label="scan.max_file_bytes"),
        max_python_ast_bytes=_positive_int(value.get("max_python_ast_bytes", 524_288), label="scan.max_python_ast_bytes"),
        max_text_probe_bytes=_positive_int(value.get("max_text_probe_bytes", 32_768), label="scan.max_text_probe_bytes"),
        max_dependency_edges=_positive_int(value.get("max_dependency_edges", 250_000), label="scan.max_dependency_edges"),
        max_files=_positive_int(value.get("max_files", 50_000), label="scan.max_files"),
        hash_algorithm=str(algorithm),
        include_suffixes=frozenset(item.casefold() for item in suffixes),
        ignore_names=frozenset(names),
        generated_markers=tuple(item.casefold() for item in markers),
    )


def _work_policy(value: Mapping[str, Any]) -> WorkPolicy:
    lanes = value.get("lane_order", ())
    if not isinstance(lanes, list) or not lanes or not all(isinstance(item, str) and item for item in lanes):
        raise MachineModelError("work.lane_order must be a non-empty string list")
    return WorkPolicy(
        lane_order=tuple(lanes),
        minimum_score=_ratio(value.get("minimum_score", 0.2), label="work.minimum_score"),
        max_candidates=_positive_int(value.get("max_candidates", 200), label="work.max_candidates"),
        max_candidates_per_subsystem=_positive_int(
            value.get("max_candidates_per_subsystem", 12),
            label="work.max_candidates_per_subsystem",
        ),
        prefer_existing_pr=_bool(value.get("prefer_existing_pr", True), label="work.prefer_existing_pr"),
        prefer_existing_issue=_bool(value.get("prefer_existing_issue", True), label="work.prefer_existing_issue"),
        prefer_targeted_test=_bool(value.get("prefer_targeted_test", True), label="work.prefer_targeted_test"),
        penalize_control_plane=_ratio(value.get("penalize_control_plane", 0.2), label="work.penalize_control_plane"),
        penalize_archive=_ratio(value.get("penalize_archive", 1.0), label="work.penalize_archive"),
        penalize_generated=_ratio(value.get("penalize_generated", 0.9), label="work.penalize_generated"),
        reward_test_gap=_ratio(value.get("reward_test_gap", 0.25), label="work.reward_test_gap"),
        reward_large_active_module=_ratio(value.get("reward_large_active_module", 0.10), label="work.reward_large_active_module"),
        reward_orphan_module=_ratio(value.get("reward_orphan_module", 0.20), label="work.reward_orphan_module"),
        reward_todo=_ratio(value.get("reward_todo", 0.10), label="work.reward_todo"),
        reward_dependency_cycle=_ratio(value.get("reward_dependency_cycle", 0.30), label="work.reward_dependency_cycle"),
        reward_high_fan_in=_ratio(value.get("reward_high_fan_in", 0.15), label="work.reward_high_fan_in"),
        reward_missing_docs=_ratio(value.get("reward_missing_docs", 0.08), label="work.reward_missing_docs"),
    )


def load_policy(root: Path | str) -> RepositoryPolicy:
    root_path = Path(root).resolve()
    machine_dir = root_path / ".machine"
    repository_data = _load_toml(machine_dir / "repository.toml")
    subsystem_data = _load_toml(machine_dir / "subsystems.toml")
    if repository_data.get("schema_version") != 1 or subsystem_data.get("schema_version") != 1:
        raise MachineModelError("unsupported machine metadata schema version")

    zones_raw = repository_data.get("zones", ())
    subsystems_raw = subsystem_data.get("subsystems", ())
    if not isinstance(zones_raw, list) or not isinstance(subsystems_raw, list):
        raise MachineModelError("zones and subsystems must be arrays of tables")

    zones = tuple(Zone.from_mapping(_require_mapping(item, label="zone")) for item in zones_raw)
    subsystems = tuple(
        Subsystem.from_mapping(_require_mapping(item, label="subsystem"))
        for item in subsystems_raw
    )
    ensure_unique_ids(zones, label="zone")
    validate_subsystem_graph(subsystems)

    policy = RepositoryPolicy(
        root=root_path,
        repository=_require_mapping(repository_data.get("repository"), label="repository"),
        scan=_scan_policy(_require_mapping(repository_data.get("scan"), label="scan")),
        work=_work_policy(_require_mapping(repository_data.get("work"), label="work")),
        raw_policy=_require_mapping(repository_data.get("policy"), label="policy"),
        outputs=_require_mapping(repository_data.get("outputs"), label="outputs"),
        zones=zones,
        subsystems=subsystems,
    )
    validate_policy(policy)
    return policy


def validate_policy(policy: RepositoryPolicy) -> None:
    for zone in policy.zones:
        for root in zone.roots:
            if any(root == excluded or root.startswith(excluded + "/") for excluded in zone.exclude_roots):
                raise MachineModelError(f"zone {zone.id!r} root is excluded by itself: {root}")

    known_roots = {
        root
        for subsystem in policy.subsystems
        for root in subsystem.roots
    }
    if not known_roots:
        raise MachineModelError("machine subsystem catalog is empty")

    active = [item for item in policy.subsystems if item.lifecycle == Lifecycle.ACTIVE]
    if not active:
        raise MachineModelError("machine subsystem catalog has no active subsystem")

    for subsystem in active:
        for dependency in subsystem.depends_on:
            target = next(item for item in policy.subsystems if item.id == dependency)
            if target.lifecycle == Lifecycle.ARCHIVE:
                raise MachineModelError(
                    f"active subsystem {subsystem.id!r} depends on archive subsystem {dependency!r}"
                )


def path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)
