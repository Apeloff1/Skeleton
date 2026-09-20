"""Bounded filesystem scanner for machine-operable repository snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable

from .model import (
    DependencyEdge,
    EdgeKind,
    FileRecord,
    FileRole,
    ImportRef,
    MachineModelError,
)
from .policy import RepositoryPolicy
from .python_analysis import analyze_python


TEXT_SUFFIXES = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".java", ".cs", ".gd", ".sh", ".bash", ".zsh",
    ".json", ".jsonl", ".toml", ".yaml", ".yml", ".md", ".txt",
    ".html", ".css", ".scss", ".sql", ".graphql", ".proto",
}
TODO_MARKERS = ("TODO", "FIXME", "XXX", "HACK", "DEPRECATED", "BUG")


@dataclass(frozen=True, slots=True)
class ScanResult:
    files: tuple[FileRecord, ...]
    edges: tuple[DependencyEdge, ...]
    findings: tuple[str, ...]
    head: str | None
    scanned_bytes: int
    skipped_bytes: int


def _git_head(root: Path) -> str | None:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    if len(value) == 40 and all(char in "0123456789abcdefABCDEF" for char in value):
        return value.casefold()
    return None


def _iter_paths(policy: RepositoryPolicy) -> Iterable[Path]:
    root = policy.root
    pending = [root]
    seen = 0
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name, reverse=True)
        except OSError as exc:
            rel = directory.relative_to(root).as_posix() if directory != root else "."
            raise MachineModelError(f"unable to scan directory {rel}: {type(exc).__name__}") from exc
        for entry in entries:
            if entry.name == ".git":
                continue
            try:
                is_link = entry.is_symlink()
                if is_link and not policy.scan.follow_symlinks:
                    yield Path(entry.path)
                    continue
                if entry.is_dir(follow_symlinks=policy.scan.follow_symlinks):
                    if policy.ignored_directory(entry.name):
                        continue
                    pending.append(Path(entry.path))
                    continue
                if entry.is_file(follow_symlinks=policy.scan.follow_symlinks):
                    yield Path(entry.path)
                    seen += 1
                    if seen > policy.scan.max_files:
                        raise MachineModelError(
                            f"repository file count exceeds scan.max_files={policy.scan.max_files}"
                        )
            except OSError as exc:
                rel = Path(entry.path).relative_to(root).as_posix()
                raise MachineModelError(f"unable to stat {rel}: {type(exc).__name__}") from exc


def _read_probe(path: Path, limit: int) -> tuple[bytes, bool]:
    try:
        with path.open("rb") as handle:
            payload = handle.read(limit + 1)
    except OSError:
        return b"", True
    return payload[:limit], b"\\x00" in payload[:limit]


def _digest(path: Path, max_bytes: int) -> str | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > max_bytes:
        return None
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(128 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def _generated(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text[:8192].casefold()
    return any(marker in lowered for marker in markers)


def _generic_todos(text: str) -> tuple[str, ...]:
    result: list[str] = []
    for line in text.splitlines():
        upper = line.upper()
        marker = next((item for item in TODO_MARKERS if item in upper), None)
        if marker is None:
            continue
        clean = " ".join(line.strip().split())[:240]
        if clean and clean not in result:
            result.append(clean)
        if len(result) >= 200:
            break
    return tuple(result)


def _decode_text(probe: bytes) -> str:
    try:
        return probe.decode("utf-8")
    except UnicodeDecodeError:
        return probe.decode("utf-8", errors="replace")


def _record(path: Path, policy: RepositoryPolicy) -> tuple[FileRecord, list[str]]:
    rel = path.relative_to(policy.root).as_posix()
    findings: list[str] = []
    try:
        stat = path.lstat()
    except OSError as exc:
        raise MachineModelError(f"unable to stat {rel}: {type(exc).__name__}") from exc

    if path.is_symlink():
        zone = policy.zone_for(rel)
        subsystem = policy.subsystem_for(rel)
        record = FileRecord(
            path=rel,
            zone_id=zone.id if zone else "unclassified",
            subsystem_id=subsystem.id if subsystem else None,
            role=FileRole.UNKNOWN,
            suffix=PurePosixPath(rel).suffix.casefold(),
            language=policy.language_for(rel),
            size_bytes=stat.st_size,
            lines=None,
            digest=None,
            generated=False,
            binary=True,
            parse_error="symlink-not-followed",
        )
        findings.append(f"symlink:{rel}")
        return record, findings

    suffix = PurePosixPath(rel).suffix.casefold()
    probe, binary = _read_probe(path, policy.scan.max_text_probe_bytes)
    text = "" if binary else _decode_text(probe)
    generated = bool(text and _generated(text, policy.scan.generated_markers))
    zone = policy.zone_for(rel)
    subsystem = policy.subsystem_for(rel)
    role = policy.role_for(rel, generated=generated)
    language = policy.language_for(rel)
    lines: int | None = None
    imports: tuple[ImportRef, ...] = ()
    symbols = ()
    todos: tuple[str, ...] = ()
    parse_error: str | None = None

    if not binary and suffix in TEXT_SUFFIXES:
        lines = text.count("\\n") + (1 if text else 0)
        todos = _generic_todos(text)
    if (
        not binary
        and suffix in {".py", ".pyi"}
        and stat.st_size <= policy.scan.max_python_ast_bytes
    ):
        try:
            full_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            parse_error = f"read:{type(exc).__name__}"
        else:
            analysis = analyze_python(full_text, filename=rel)
            lines = analysis.lines
            imports = analysis.imports
            symbols = analysis.symbols
            todos = analysis.todos
            parse_error = analysis.parse_error

    digest = _digest(path, policy.scan.max_file_bytes)
    record = FileRecord(
        path=rel,
        zone_id=zone.id if zone else "unclassified",
        subsystem_id=subsystem.id if subsystem else None,
        role=role,
        suffix=suffix,
        language=language,
        size_bytes=stat.st_size,
        lines=lines,
        digest=digest,
        generated=generated,
        binary=binary,
        imports=imports,
        symbols=symbols,
        todos=todos,
        parse_error=parse_error,
    )

    if zone is None and role in {FileRole.SOURCE, FileRole.TEST, FileRole.WORKFLOW, FileRole.SCRIPT}:
        findings.append(f"unclassified-zone:{rel}")
    if subsystem is None and role == FileRole.SOURCE and not record.generated:
        findings.append(f"unowned-active-source:{rel}")
    if parse_error:
        findings.append(f"parse-error:{rel}:{parse_error}")
    return record, findings


def _module_index(files: Iterable[FileRecord]) -> dict[str, str]:
    result: dict[str, str] = {}
    for file in files:
        module = file.module_name
        if module:
            result[module] = file.path
    return result


def _package_parts(file: FileRecord) -> list[str]:
    module = file.module_name
    if module is None:
        return []
    parts = module.split(".")
    if PurePosixPath(file.path).name not in {"__init__.py", "__init__.pyi"}:
        parts = parts[:-1]
    return parts


def resolve_python_import(
    file: FileRecord,
    ref: ImportRef,
    modules: dict[str, str],
) -> tuple[str | None, bool]:
    module = ref.module
    if ref.level:
        package = _package_parts(file)
        climb = ref.level - 1
        if climb > len(package):
            return None, True
        base = package[: len(package) - climb] if climb else package
        module = ".".join([*base, *([ref.module] if ref.module else [])])
    if not module:
        return None, True

    candidate = module
    while candidate:
        if candidate in modules:
            return modules[candidate], False
        candidate = candidate.rpartition(".")[0]
    return module, True


def build_import_edges(
    files: Iterable[FileRecord],
    *,
    max_edges: int,
) -> tuple[DependencyEdge, ...]:
    materialized = tuple(files)
    modules = _module_index(materialized)
    edges: list[DependencyEdge] = []
    for file in materialized:
        if not file.imports:
            continue
        for ref in file.imports:
            target, external = resolve_python_import(file, ref, modules)
            if target is None:
                continue
            edges.append(
                DependencyEdge(
                    source=file.path,
                    target=target,
                    kind=EdgeKind.IMPORT,
                    detail=ref.module,
                    line=ref.line,
                    external=external,
                )
            )
            if len(edges) >= max_edges:
                return tuple(edges)
    edges.sort(key=lambda item: (item.source, item.target, item.line or 0, item.detail))
    return tuple(edges)


def scan_repository(policy: RepositoryPolicy) -> ScanResult:
    records: list[FileRecord] = []
    findings: list[str] = []
    scanned_bytes = 0
    skipped_bytes = 0
    for path in _iter_paths(policy):
        record, local_findings = _record(path, policy)
        records.append(record)
        findings.extend(local_findings)
        if record.digest is not None or (
            not record.binary and record.suffix in TEXT_SUFFIXES
        ):
            scanned_bytes += record.size_bytes
        else:
            skipped_bytes += record.size_bytes

    records.sort(key=lambda item: item.path)
    edges = build_import_edges(records, max_edges=policy.scan.max_dependency_edges)
    return ScanResult(
        files=tuple(records),
        edges=edges,
        findings=tuple(sorted(set(findings))),
        head=_git_head(policy.root),
        scanned_bytes=scanned_bytes,
        skipped_bytes=skipped_bytes,
    )
