"""SHA-bound, no-execution Python import graph for offline Jeeves patches.

The existing static parser proves syntax, but not whether a generated source
change references other changed files or uses impossible relative-import
levels. This module inspects ONLY the reviewed replacement Python AST and
returns a bounded source-to-source dependency graph. Original unmodified
project files, stdlib and external packages are not inspected or assumed to
exist; those imports are explicitly UNVERIFIED, never called resolved.

It does not import or compile generated code, execute packages, use network,
start Git, read arbitrary project source, or grant any model tools.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath

from .desktop_patch_bundle import PatchEntry, PortablePatchPlan
from .desktop_workspace import _canonical

SCHEMA = "jeeves.workspace.python-source-graph.v1"
MAX_PYTHON_FILES = 24
MAX_IMPORTS_PER_FILE = 256
MAX_TOTAL_IMPORTS = 1024
MAX_GRAPH_COMPONENTS = 24
MAX_RECURSION_LEVEL = 32


class SourceGraphHold(ValueError):
    """Untrusted Python source graph cannot establish finite AST provenance."""


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _digest(x: object) -> bool:
    return (
        type(x) is str and len(x) == 64
        and all(c in "0123456789abcdef" for c in x)
    )


def _module_path(path: str) -> str:
    leaf = PurePosixPath(path)
    if leaf.suffix not in (".py", ".pyi"):
        raise SourceGraphHold("not a Python source module")
    parts = list(leaf.parts)
    if parts[-1] in ("__init__.py", "__init__.pyi"):
        parts.pop()
    else:
        parts[-1] = parts[-1].rsplit(".", 1)[0]
    if not parts:
        # A top-level __init__.py is still parseable source, but the
        # package identity outside this selected project is unknown.
        # Keep a bounded synthetic graph node, not a false import pass.
        return "__root__"
    if any(not p or p.startswith(".") for p in parts):
        raise SourceGraphHold("invalid Python package module path")
    return ".".join(parts)


def _parent_package(path: str) -> tuple[str, ...]:
    if PurePosixPath(path).name in ("__init__.py", "__init__.pyi"):
        return tuple(_module_path(path).split("."))
    components = _module_path(path).split(".")
    return tuple(components[:-1])


@dataclass(frozen=True, slots=True)
class ImportLink:
    source_path: str
    source_sha256: str
    requested_name_sha256: str
    target_path: str | None
    status: str
    line: int
    relative_level: int

    def __post_init__(self):
        if (
            type(self.source_path) is not str or not self.source_path
            or not _digest(self.source_sha256)
            or not _digest(self.requested_name_sha256)
            or self.status not in (
                "linked-reviewed-source",
                "unverified-original-or-external",
                "invalid-relative-import",
            )
            or (
                self.target_path is not None
                and (
                    self.status != "linked-reviewed-source"
                    or type(self.target_path) is not str
                    or not self.target_path
                )
            )
            or (
                self.status == "linked-reviewed-source"
                and self.target_path is None
            )
            or type(self.line) is not int
            or not 1 <= self.line <= 1000000
            or type(self.relative_level) is not int
            or not 0 <= self.relative_level <= MAX_RECURSION_LEVEL
        ):
            raise SourceGraphHold("untrusted original Python source dependency")

    def public(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "requested_name_sha256": self.requested_name_sha256,
            "target_path": self.target_path,
            "status": self.status,
            "line": self.line,
            "relative_level": self.relative_level,
            "generated_source_executed": False,
        }


@dataclass(frozen=True, slots=True)
class PythonFileGraph:
    path: str
    source_sha256: str
    module_name_sha256: str
    status: str
    import_links: tuple[ImportLink, ...]
    python_ast_nodes: int

    def __post_init__(self):
        if (
            type(self.path) is not str or not self.path
            or not _digest(self.source_sha256)
            or not _digest(self.module_name_sha256)
            or self.status not in ("parsed", "syntax-held", "unverified-size")
            or type(self.import_links) is not tuple
            or len(self.import_links) > MAX_IMPORTS_PER_FILE
            or any(
                type(i) is not ImportLink
                or i.source_path != self.path
                or i.source_sha256 != self.source_sha256
                for i in self.import_links
            )
            or type(self.python_ast_nodes) is not int
            or self.python_ast_nodes < 0 or self.python_ast_nodes > 50000
        ):
            raise SourceGraphHold("untrusted bounded import graph file entry")

    def public(self) -> dict[str, object]:
        return {
            "path": self.path,
            "source_sha256": self.source_sha256,
            "module_name_sha256": self.module_name_sha256,
            "status": self.status,
            "python_ast_nodes": self.python_ast_nodes,
            "import_links": [x.public() for x in self.import_links],
            "source_code_executed": False,
        }


@dataclass(frozen=True, slots=True)
class PythonSourceGraph:
    manifest_sha256: str
    patch_sha256: str
    python_files: tuple[PythonFileGraph, ...]
    cycles: tuple[tuple[str, ...], ...]
    graph_sha256: str
    status: str

    def __post_init__(self):
        if (
            not _digest(self.manifest_sha256)
            or not _digest(self.patch_sha256)
            or not _digest(self.graph_sha256)
            or type(self.python_files) is not tuple
            or len(self.python_files) > MAX_PYTHON_FILES
            or any(type(f) is not PythonFileGraph for f in self.python_files)
            or len({f.path.casefold() for f in self.python_files}) != len(self.python_files)
            or type(self.cycles) is not tuple
            or len(self.cycles) > MAX_GRAPH_COMPONENTS
            or any(type(x) is not tuple or not 1 <= len(x) <= MAX_GRAPH_COMPONENTS
                   for x in self.cycles)
            or self.status not in (
                "observed-internal-imports",
                "partially-unverified-imports",
                "invalid-relative-held",
                "unsupported-python-source-held",
                "no-python-source",
            )
        ):
            raise SourceGraphHold("unverified Python graph provenance")
        if _sha(_canonical(self._core())) != self.graph_sha256:
            raise SourceGraphHold("original Python import graph changed after review")
        expected = (
            "no-python-source" if not self.python_files
            else "unsupported-python-source-held"
            if any(f.status != "parsed" for f in self.python_files)
            else "invalid-relative-held"
            if self.invalid_relative_count
            else "partially-unverified-imports"
            if self.unverified_import_count else "observed-internal-imports"
        )
        if self.status != expected:
            raise SourceGraphHold("dependency analysis incorrectly certified a source")

    def _core(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "manifest_sha256": self.manifest_sha256,
            "patch_sha256": self.patch_sha256,
            "python_files": [x.public() for x in self.python_files],
            "cycles": [list(x) for x in self.cycles],
        }

    @property
    def linked_import_count(self) -> int:
        return sum(i.status == "linked-reviewed-source"
                   for f in self.python_files for i in f.import_links)

    @property
    def unverified_import_count(self) -> int:
        return sum(i.status == "unverified-original-or-external"
                   for f in self.python_files for i in f.import_links)

    @property
    def invalid_relative_count(self) -> int:
        return sum(i.status == "invalid-relative-import"
                   for f in self.python_files for i in f.import_links)

    @property
    def permits_inert_export(self) -> bool:
        return self.status not in (
            "unsupported-python-source-held", "invalid-relative-held",
        )

    def to_public(self) -> dict[str, object]:
        return {
            **self._core(),
            "graph_sha256": self.graph_sha256,
            "status": self.status,
            "python_file_count": len(self.python_files),
            "linked_reviewed_source_import_count": self.linked_import_count,
            "unverified_original_or_external_import_count":
                self.unverified_import_count,
            "invalid_relative_import_count": self.invalid_relative_count,
            "observed_cycle_count": len(self.cycles),
            "inert_export_eligible": self.permits_inert_export,
            "whole_original_project_scanned": False,
            "all_dependencies_resolved": False,
            "source_code_executed": False,
            "python_imports_executed": False,
            "python_compiler_executed": False,
            "release_certified": False,
        }


def _link(
    entry: PatchEntry, requested: str, level: int, line: int,
    targets: dict[str, str], *, invalid: bool = False,
) -> ImportLink:
    target = targets.get(requested)
    return ImportLink(
        source_path=entry.path,
        source_sha256=entry.replacement_sha256,
        requested_name_sha256=_sha(requested.encode("utf-8", "strict")),
        target_path=target if not invalid else None,
        status=(
            "invalid-relative-import" if invalid
            else "linked-reviewed-source" if target is not None
            else "unverified-original-or-external"
        ),
        line=line, relative_level=level,
    )


def _imports(
    entry: PatchEntry, targets: dict[str, str],
) -> PythonFileGraph:
    module = _module_path(entry.path)
    name_sha = _sha(module.encode("utf-8", "strict"))
    try:
        parsed = ast.parse(entry.replacement_text, mode="exec", type_comments=True)
    except (SyntaxError, RecursionError, MemoryError, UnicodeError, ValueError):
        return PythonFileGraph(
            path=entry.path, source_sha256=entry.replacement_sha256,
            module_name_sha256=name_sha, status="syntax-held",
            import_links=(), python_ast_nodes=0,
        )
    nodes = 0
    links = []
    try:
        for node in ast.walk(parsed):
            nodes += 1
            if nodes > 50000:
                return PythonFileGraph(
                    path=entry.path, source_sha256=entry.replacement_sha256,
                    module_name_sha256=name_sha, status="unverified-size",
                    import_links=(), python_ast_nodes=50000,
                )
            if isinstance(node, ast.Import):
                for item in node.names:
                    links.append(_link(
                        entry, item.name, 0, node.lineno, targets,
                    ))
            elif isinstance(node, ast.ImportFrom):
                parent = _parent_package(entry.path)
                level = node.level
                if level > 0 and (
                    level > len(parent) or level > MAX_RECURSION_LEVEL
                ):
                    requested = "invalid-relative-level-" + str(level)
                    links.append(_link(
                        entry, requested, min(level, MAX_RECURSION_LEVEL),
                        node.lineno, targets, invalid=True,
                    ))
                    continue
                base = ".".join(
                    (*parent[:len(parent) - level + 1],
                     *(node.module.split(".") if node.module else ())),
                ) if level else (node.module or "")
                for item in node.names:
                    candidate = base + "." + item.name if base else item.name
                    # from package import module: first check package.module;
                    # from ordinary_module import symbol: check module.
                    selected = candidate if candidate in targets else base
                    if not selected:
                        selected = candidate
                    links.append(_link(
                        entry, selected, level, node.lineno, targets,
                    ))
            if len(links) > MAX_IMPORTS_PER_FILE:
                return PythonFileGraph(
                    path=entry.path, source_sha256=entry.replacement_sha256,
                    module_name_sha256=name_sha, status="unverified-size",
                    import_links=(), python_ast_nodes=nodes,
                )
    except (UnicodeError, ValueError, TypeError, RecursionError):
        return PythonFileGraph(
            path=entry.path, source_sha256=entry.replacement_sha256,
            module_name_sha256=name_sha, status="syntax-held",
            import_links=(), python_ast_nodes=0,
        )
    return PythonFileGraph(
        path=entry.path, source_sha256=entry.replacement_sha256,
        module_name_sha256=name_sha, status="parsed",
        import_links=tuple(links), python_ast_nodes=nodes,
    )


def _cycles(files: tuple[PythonFileGraph, ...]) -> tuple[tuple[str, ...], ...]:
    """No code execution, just at most 24 static graph nodes."""
    sources = {f.path for f in files}
    edges = {
        f.path: {
            x.target_path for x in f.import_links
            if x.target_path in sources and x.status == "linked-reviewed-source"
        } for f in files
    }
    visiting = set()
    visited = set()
    path = []
    detected = set()
    def explore(node):
        if node in visiting:
            try:
                index = path.index(node)
            except ValueError:
                return
            members = tuple(sorted(set(path[index:])))
            if members:
                detected.add(members)
            return
        if node in visited:
            return
        visiting.add(node)
        path.append(node)
        for nxt in sorted(edges.get(node, ())):
            explore(nxt)
        path.pop()
        visiting.remove(node)
        visited.add(node)
    for file in sorted(sources):
        explore(file)
    return tuple(sorted(detected))


def analyze_python_source_graph(plan: PortablePatchPlan) -> PythonSourceGraph:
    """Pure bounded AST analysis bound to the entire original patch identity."""
    if type(plan) is not PortablePatchPlan:
        raise SourceGraphHold("entire reviewed source plan required")
    plan.__post_init__()
    python_files = tuple(
        f for f in plan.entries if PurePosixPath(f.path).suffix in (".py", ".pyi")
    )
    if len(python_files) > MAX_PYTHON_FILES:
        raise SourceGraphHold("too many original Python modules")
    # A real package may legitimately include both executable .py and a
    # type-only .pyi stub for the SAME module. Prefer the implementation
    # for import graph edges; still parse and hash both original files.
    # Other duplicate package claims (pkg.py vs pkg/__init__.py) hold.
    targets: dict[str, str] = {}
    for file in python_files:
        name = _module_path(file.path)
        prior = targets.get(name)
        if prior is None:
            targets[name] = file.path
        elif (
            prior.endswith(".py")
            and file.path == prior + "i"
        ):
            continue
        elif prior.endswith(".pyi") and prior[:-1] == file.path:
            targets[name] = file.path
        else:
            raise SourceGraphHold(
                "two reviewed implementation paths claim the same Python module",
            )
    found = tuple(_imports(file, targets) for file in python_files)
    if sum(len(f.import_links) for f in found) > MAX_TOTAL_IMPORTS:
        raise SourceGraphHold("aggregate Python import graph exceeds source budget")
    cycles = _cycles(found)
    first = "no-python-source" if not found else (
        "unsupported-python-source-held"
        if any(f.status != "parsed" for f in found)
        else "invalid-relative-held"
        if any(x.status == "invalid-relative-import"
               for f in found for x in f.import_links)
        else "partially-unverified-imports"
        if any(x.status == "unverified-original-or-external"
               for f in found for x in f.import_links)
        else "observed-internal-imports"
    )
    core = {
        "schema": SCHEMA,
        "manifest_sha256": plan.manifest_sha256,
        "patch_sha256": plan.patch_sha256,
        "python_files": [f.public() for f in found],
        "cycles": [list(x) for x in cycles],
    }
    return PythonSourceGraph(
        manifest_sha256=plan.manifest_sha256,
        patch_sha256=plan.patch_sha256,
        python_files=found, cycles=cycles,
        graph_sha256=_sha(_canonical(core)),
        status=first,
    )


__all__ = [
    "SCHEMA", "SourceGraphHold", "ImportLink", "PythonFileGraph",
    "PythonSourceGraph", "analyze_python_source_graph",
]
