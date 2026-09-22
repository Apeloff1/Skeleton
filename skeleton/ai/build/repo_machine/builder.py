"""Deterministic repository scanner, classifier and topology builder."""
from __future__ import annotations

import ast
from collections import defaultdict
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Iterable

from .config import MachineConfig, load_machine_config
from .model import (
    FileRecord,
    Finding,
    RepositoryModel,
    SubsystemRecord,
    TopologyEdge,
    unique_findings,
)

_CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp"}
_DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
_CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
_SCRIPT_SUFFIXES = {".sh", ".ps1", ".bat"}
_JS_IMPORT = re.compile(r"(?:from\s+|require\s*\(|import\s*\()[\"']([^\"']+)")
_JAVA_IMPORT = re.compile(r"^\s*import\s+([A-Za-z0-9_.]+)", re.MULTILINE)


def _posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.casefold()
    return {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".java": "java",
        ".go": "go", ".rs": "rust", ".c": "c", ".cc": "cpp",
        ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".sh": "shell",
        ".ps1": "powershell", ".md": "markdown", ".mdx": "markdown",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    }.get(suffix, "other")


def _kind(path: str) -> str:
    lower = path.casefold()
    name = PurePosixPath(lower).name
    suffix = PurePosixPath(lower).suffix
    if lower.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
        return "workflow"
    if "/tests/" in f"/{lower}/" or name.startswith("test_") or ".test." in name or ".spec." in name:
        return "test"
    if suffix in _CODE_SUFFIXES:
        return "source"
    if suffix in _DOC_SUFFIXES or name.startswith(("readme", "contributing", "security")):
        return "docs"
    if suffix in _SCRIPT_SUFFIXES:
        return "script"
    if suffix in _CONFIG_SUFFIXES:
        return "config"
    if suffix in {".csv", ".jsonl", ".sql", ".xml"}:
        return "data"
    return "unknown"


def _python_metadata(content: str) -> tuple[int, tuple[str, ...]]:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, TypeError):
        return 0, ()
    symbols = 0
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols += 1
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            if prefix:
                imports.add(prefix)
    return symbols, tuple(sorted(imports))


def _generic_imports(language: str, content: str) -> tuple[str, ...]:
    if language in {"javascript", "typescript"}:
        return tuple(sorted(set(match.group(1) for match in _JS_IMPORT.finditer(content))))
    if language == "java":
        return tuple(sorted(set(match.group(1) for match in _JAVA_IMPORT.finditer(content))))
    return ()


def _test_target(path: str) -> str | None:
    p = PurePosixPath(path)
    name = p.name
    if name.startswith("test_") and name.endswith(".py"):
        return name[5:-3]
    for marker in (".test.", ".spec."):
        if marker in name:
            return name.split(marker, 1)[0]
    return None


def _internal_target(import_name: str, source_path: str, files: set[str]) -> str | None:
    if not import_name:
        return None
    if import_name.startswith(".") and source_path.endswith(".py"):
        source_parts = PurePosixPath(source_path).parts[:-1]
        level = len(import_name) - len(import_name.lstrip("."))
        module = import_name[level:]
        base = source_parts[: max(0, len(source_parts) - level + 1)]
        parts = (*base, *module.split(".")) if module else base
    else:
        parts = tuple(part for part in import_name.split(".") if part)
    if not parts:
        return None
    candidates = [
        "/".join(parts) + ".py",
        "/".join(parts) + "/__init__.py",
        "/".join(parts) + ".ts",
        "/".join(parts) + ".tsx",
        "/".join(parts) + ".js",
        "/".join(parts) + ".jsx",
        "/".join(parts) + ".java",
    ]
    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def _tarjan(nodes: Iterable[str], adjacency: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    low: dict[str, int] = {}
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(adjacency.get(node, ())):
            if target not in indexes:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indexes[target])
        if low[node] == indexes[node]:
            component: list[str] = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                components.append(tuple(sorted(component)))

    for node in sorted(set(nodes)):
        if node not in indexes:
            visit(node)
    return tuple(sorted(components))


class RepositoryModelBuilder:
    def __init__(self, root: str | Path, config: MachineConfig | None = None) -> None:
        self.root = Path(root).resolve()
        self.config = config or load_machine_config(self.root)

    def _ignored(self, path: str) -> bool:
        return any(path == p.rstrip("/") or path.startswith(p) for p in self.config.ignore_prefixes) or any(
            path.endswith(suffix) for suffix in self.config.ignore_suffixes
        )

    def _zone(self, path: str) -> tuple[str, str, str]:
        for rule in self.config.zones:
            if rule.matches(path):
                return rule.name, rule.owner, rule.criticality
        return "unclassified", self.config.default_owner, "medium"

    def _iter_files(self) -> tuple[list[Path], bool]:
        result: list[Path] = []
        truncated = False
        for directory, names, filenames in os.walk(self.root):
            base = Path(directory)
            rel_dir = "" if base == self.root else _posix(base, self.root) + "/"
            names[:] = sorted(
                name for name in names
                if not self._ignored(rel_dir + name + "/")
            )
            for name in sorted(filenames):
                path = base / name
                rel = _posix(path, self.root)
                if self._ignored(rel):
                    continue
                result.append(path)
                if len(result) >= self.config.max_files:
                    truncated = True
                    return result, truncated
        return result, truncated

    def _record(self, path: Path) -> FileRecord:
        rel = _posix(path, self.root)
        zone, owner, _criticality = self._zone(rel)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("repository inventory only accepts regular files")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("repository file cannot be resolved") from exc
        if not resolved.is_relative_to(self.root):
            raise ValueError("repository file escapes repository root")

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("repository inventory only accepts regular files")
            if before.st_size > self.config.max_file_bytes:
                content = ""
                digest_value = hashlib.sha256(
                    f"<oversize:{before.st_size}>".encode("ascii")
                ).hexdigest()
                lines = 0
            else:
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    raw = handle.read(self.config.max_file_bytes + 1)
                after = os.fstat(fd)
                if (
                    before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                ):
                    raise OSError("repository file changed during scan")
                if len(raw) > self.config.max_file_bytes:
                    raise OSError("repository file exceeded scan bound during read")
                digest_value = hashlib.sha256(raw).hexdigest()
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    content = ""
                lines = len(content.splitlines()) if content else 0
            file_size = before.st_size
        finally:
            os.close(fd)
        language = _language(rel)
        symbols = 0
        imports: tuple[str, ...] = ()
        if content and language == "python":
            symbols, imports = _python_metadata(content)
        elif content:
            imports = _generic_imports(language, content)
        return FileRecord(
            path=rel,
            zone=zone,
            owner=owner,
            kind=_kind(rel),
            language=language,
            size=file_size,
            lines=lines,
            sha256=digest_value,
            symbols=symbols,
            imports=imports,
            test_target=_test_target(rel),
        )

    def build(self) -> RepositoryModel:
        paths, truncated = self._iter_files()
        records: list[FileRecord] = []
        findings: list[Finding] = []
        for path in paths:
            try:
                record = self._record(path)
            except (OSError, ValueError):
                rel = _posix(path, self.root)
                zone, _owner, _criticality = self._zone(rel)
                findings.append(Finding(
                    code="scan.unreadable", severity="medium", zone=zone,
                    path=rel, detail="file could not be safely indexed",
                ))
                continue
            records.append(record)

        path_set = {record.path for record in records}
        by_path = {record.path: record for record in records}
        edge_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        for record in records:
            for imported in record.imports:
                target_path = _internal_target(imported, record.path, path_set)
                if target_path is None:
                    continue
                target = by_path[target_path]
                if target.zone == record.zone:
                    continue
                edge_counts[(record.zone, target.zone, "import")] += 1
        edges = tuple(
            TopologyEdge(source, target, kind, count)
            for (source, target, kind), count in sorted(edge_counts.items())
        )

        zone_rules = {rule.name: rule for rule in self.config.zones}
        zones = sorted({record.zone for record in records} | set(zone_rules))
        dependencies: dict[str, set[str]] = defaultdict(set)
        dependents: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            dependencies[edge.source].add(edge.target)
            dependents[edge.target].add(edge.source)

        subsystems: list[SubsystemRecord] = []
        for zone in zones:
            members = [record for record in records if record.zone == zone]
            rule = zone_rules.get(zone)
            owner = rule.owner if rule else self.config.default_owner
            criticality = rule.criticality if rule else "medium"
            entrypoints = tuple(sorted(
                record.path for record in members
                if PurePosixPath(record.path).name in {
                    "__main__.py", "main.py", "server.py", "app.py", "cli.py",
                    "index.ts", "index.js", "package.json",
                }
            )[:32])
            subsystems.append(SubsystemRecord(
                name=zone,
                owner=owner,
                criticality=criticality,
                file_count=len(members),
                code_files=sum(record.kind == "source" for record in members),
                test_files=sum(record.kind == "test" for record in members),
                workflow_files=sum(record.kind == "workflow" for record in members),
                total_lines=sum(record.lines for record in members),
                total_bytes=sum(record.size for record in members),
                languages=tuple(sorted({record.language for record in members if record.language != "other"})),
                entrypoints=entrypoints,
                dependencies=tuple(sorted(dependencies[zone])),
                dependents=tuple(sorted(dependents[zone])),
            ))

        adjacency = {zone: set(dependencies[zone]) for zone in zones}
        cycles = _tarjan(zones, adjacency) if self.config.detect_dependency_cycles else ()
        for cycle in cycles:
            severity = "high" if any((zone_rules.get(z) and zone_rules[z].criticality == "critical") for z in cycle) else "medium"
            findings.append(Finding(
                code="topology.cycle", severity=severity, zone=cycle[0],
                detail="cross-zone dependency cycle", evidence=cycle,
            ))

        for record in records:
            if record.zone == "unclassified":
                findings.append(Finding(
                    code="organization.unclassified", severity="low", zone="unclassified",
                    path=record.path, detail="file does not match a declared machine zone",
                ))
            if self.config.detect_oversized_modules and record.kind == "source":
                threshold = self.config.oversized_generic_lines
                if record.language == "python":
                    threshold = self.config.oversized_python_lines
                elif record.language in {"javascript", "typescript"}:
                    threshold = self.config.oversized_javascript_lines
                if record.lines > threshold:
                    findings.append(Finding(
                        code="organization.oversized-module", severity="medium", zone=record.zone,
                        path=record.path,
                        detail=f"{record.lines} lines exceeds machine threshold {threshold}",
                    ))

        if self.config.require_tests_for_code:
            for subsystem in subsystems:
                if subsystem.code_files >= 4 and subsystem.test_files == 0:
                    findings.append(Finding(
                        code="quality.missing-zone-tests",
                        severity="high" if subsystem.criticality in {"critical", "high"} else "medium",
                        zone=subsystem.name,
                        detail=f"{subsystem.code_files} code files and no classified tests",
                    ))

        if truncated:
            findings.append(Finding(
                code="scan.truncated", severity="high", zone="unclassified",
                detail=f"repository scan hit max_files={self.config.max_files}",
            ))

        return RepositoryModel(
            schema_version=self.config.schema_version,
            repository=self.config.name,
            files=tuple(sorted(records, key=lambda item: item.path)),
            subsystems=tuple(sorted(subsystems, key=lambda item: item.name)),
            edges=edges,
            findings=unique_findings(findings),
            cycles=cycles,
            unclassified_count=sum(record.zone == "unclassified" for record in records),
            truncated=truncated,
            metadata={
                "file_count": len(records),
                "total_lines": sum(record.lines for record in records),
                "total_bytes": sum(record.size for record in records),
                "zone_count": len(subsystems),
            },
        )


def build_repository_model(root: str | Path = ".") -> RepositoryModel:
    return RepositoryModelBuilder(root).build()
