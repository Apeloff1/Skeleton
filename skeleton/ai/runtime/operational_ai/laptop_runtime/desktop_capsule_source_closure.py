"""Bounded Python closure over *selected* original + reviewed Jeeves changes.

The prior patch-only graph cannot establish whether imports into unchanged
project files are present in the private source capsule. This additional
read-only AST graph links only source bytes explicitly selected by the human
and the exact new/edit replacements already SHA-reviewed by the workbench.

No import resolution hits disk, model, package index, sys.path, network or
Python importer. Unknown dynamic/stdlib/external/unselected imports remain
UNVERIFIED, even if a package is installed on the operator's laptop.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath

from .desktop_source_graph import _module_path, _parent_package
from .desktop_workspace import _canonical, _relative, WorkspaceDeliveryHold

SCHEMA = "jeeves.workspace.selected-python-closure.v1"
MAX_SOURCE_FILES = 72
MAX_PYTHON_FILES = 72
MAX_SOURCE_BYTES = 1572864
MAX_NODES_PER_FILE = 50000
MAX_TOTAL_NODES = 120000
MAX_IMPORTS_PER_FILE = 256
MAX_TOTAL_IMPORTS = 2048
MAX_CYCLES = 72
_KINDS = frozenset(("new", "edit", "selected-original"))


class CapsuleClosureHold(ValueError):
    """Untrusted, incomplete or oversized explicit Python source graph."""


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


@dataclass(frozen=True, slots=True)
class ClosureSource:
    path: str
    kind: str
    raw: bytes
    sha256: str

    def __post_init__(self):
        try:
            _relative(self.path)
        except WorkspaceDeliveryHold as exc:
            raise CapsuleClosureHold("invalid source-relative Python module path") from exc
        if (
            type(self.kind) is not str or self.kind not in _KINDS
            or type(self.raw) is not bytes or not 1 <= len(self.raw) <= 65536
            or not _sha(self.sha256) or _hash(self.raw) != self.sha256
        ):
            raise CapsuleClosureHold("selected or generated source identity changed")

    @property
    def python(self) -> bool:
        return PurePosixPath(self.path).suffix in (".py", ".pyi")


@dataclass(frozen=True, slots=True)
class ClosureImport:
    source_path: str
    source_sha256: str
    source_kind: str
    import_sha256: str
    target_path: str | None
    target_sha256: str | None
    target_kind: str | None
    level: int
    line: int
    status: str

    def __post_init__(self):
        if (
            type(self.source_path) is not str or not self.source_path
            or not _sha(self.source_sha256) or not _sha(self.import_sha256)
            or self.source_kind not in _KINDS
            or type(self.level) is not int or not 0 <= self.level <= 32
            or type(self.line) is not int or not 1 <= self.line <= 1000000
            or self.status not in (
                "linked-review-change",
                "linked-selected-original",
                "unverified-external-or-unselected",
                "invalid-relative-level",
            )
        ):
            raise CapsuleClosureHold("untrusted source import proof")
        if self.status.startswith("linked-"):
            if (
                type(self.target_path) is not str or not self.target_path
                or not _sha(self.target_sha256) or self.target_kind not in _KINDS
            ):
                raise CapsuleClosureHold("linked source import missing SHA-bound target")
            if self.status == "linked-selected-original" and self.target_kind != "selected-original":
                raise CapsuleClosureHold("selected import provenance changed")
            if self.status == "linked-review-change" and self.target_kind == "selected-original":
                raise CapsuleClosureHold("changed import provenance changed")
        elif any(
            value is not None
            for value in (self.target_path, self.target_sha256, self.target_kind)
        ):
            raise CapsuleClosureHold("unverified import cannot invent a target")

    def public(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_kind": self.source_kind,
            "requested_import_sha256": self.import_sha256,
            "target_path": self.target_path,
            "target_sha256": self.target_sha256,
            "target_kind": self.target_kind,
            "relative_level": self.level,
            "line": self.line,
            "status": self.status,
            "source_or_dependency_executed": False,
        }


@dataclass(frozen=True, slots=True)
class CapsuleClosure:
    source_manifest_sha256: str
    source_patch_sha256: str
    sources_sha256: str
    graph_sha256: str
    python_count: int
    ast_nodes: int
    import_links: tuple[ClosureImport, ...]
    cycles: tuple[tuple[str, ...], ...]
    status: str

    def __post_init__(self):
        if (
            any(not _sha(x) for x in (
                self.source_manifest_sha256, self.source_patch_sha256,
                self.sources_sha256, self.graph_sha256,
            ))
            or type(self.python_count) is not int
            or not 0 <= self.python_count <= MAX_PYTHON_FILES
            or type(self.ast_nodes) is not int
            or not 0 <= self.ast_nodes <= MAX_TOTAL_NODES
            or type(self.import_links) is not tuple
            or len(self.import_links) > MAX_TOTAL_IMPORTS
            or any(type(x) is not ClosureImport for x in self.import_links)
            or type(self.cycles) is not tuple
            or len(self.cycles) > MAX_CYCLES
            or any(type(cycle) is not tuple or not cycle
                   or len(cycle) > MAX_SOURCE_FILES for cycle in self.cycles)
            or self.status not in (
                "no-selected-python", "linked-selected-python",
                "partially-unverified-python", "invalid-relative-held",
            )
            or self.graph_sha256 != _hash(_canonical(self._core()))
        ):
            raise CapsuleClosureHold("source capsule graph receipt or digest changed")
        inferred = (
            "no-selected-python" if self.python_count == 0
            else "invalid-relative-held" if self.invalid_relative_count > 0
            else "partially-unverified-python" if self.unverified_count > 0
            else "linked-selected-python"
        )
        if inferred != self.status:
            raise CapsuleClosureHold("unverified import was falsely marked resolved")

    @property
    def linked_original_count(self) -> int:
        return sum(x.status == "linked-selected-original" for x in self.import_links)

    @property
    def linked_change_count(self) -> int:
        return sum(x.status == "linked-review-change" for x in self.import_links)

    @property
    def unverified_count(self) -> int:
        return sum(
            x.status == "unverified-external-or-unselected"
            for x in self.import_links
        )

    @property
    def invalid_relative_count(self) -> int:
        return sum(x.status == "invalid-relative-level" for x in self.import_links)

    @property
    def permits_inert_capsule(self) -> bool:
        return self.status != "invalid-relative-held"

    def _core(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_patch_sha256": self.source_patch_sha256,
            "sources_sha256": self.sources_sha256,
            "python_count": self.python_count,
            "ast_nodes": self.ast_nodes,
            "import_links": [e.public() for e in self.import_links],
            "cycles": [list(c) for c in self.cycles],
        }

    def to_public(self) -> dict[str, object]:
        return {
            **self._core(),
            "graph_sha256": self.graph_sha256,
            "status": self.status,
            "linked_selected_original_imports": self.linked_original_count,
            "linked_review_change_imports": self.linked_change_count,
            "unverified_external_or_unselected_imports": self.unverified_count,
            "invalid_relative_imports": self.invalid_relative_count,
            "observed_cycle_count": len(self.cycles),
            "permits_inert_capsule": self.permits_inert_capsule,
            "all_original_project_imports_known": False,
            "stdlib_or_external_dependencies_verified": False,
            "runtime_imports_executed": False,
            "source_code_executed": False,
            "release_certified": False,
        }


def _source_set(sources: tuple[ClosureSource, ...]) -> tuple[
    dict[str, ClosureSource], dict[str, ClosureSource],
]:
    if (
        type(sources) is not tuple or not 1 <= len(sources) <= MAX_SOURCE_FILES
        or any(type(x) is not ClosureSource for x in sources)
    ):
        raise CapsuleClosureHold("one to 72 explicit reviewed source files required")
    if len({x.path.casefold() for x in sources}) != len(sources):
        raise CapsuleClosureHold("source capsule contains case-colliding filenames")
    if sum(len(x.raw) for x in sources) > MAX_SOURCE_BYTES:
        raise CapsuleClosureHold("source corpus exceeds bounded audit budget")
    by_path: dict[str, ClosureSource] = {}
    module_map: dict[str, ClosureSource] = {}
    for entry in sources:
        entry.__post_init__()
        by_path[entry.path] = entry
        if not entry.python:
            continue
        module = _module_path(entry.path)
        current = module_map.get(module)
        if current is None:
            module_map[module] = entry
        elif PurePosixPath(current.path).suffix == ".pyi" and (
            PurePosixPath(entry.path).suffix == ".py"
            and current.path.rsplit(".", 1)[0] == entry.path.rsplit(".", 1)[0]
        ):
            module_map[module] = entry
        elif PurePosixPath(entry.path).suffix == ".pyi" and (
            PurePosixPath(current.path).suffix == ".py"
            and current.path.rsplit(".", 1)[0] == entry.path.rsplit(".", 1)[0]
        ):
            continue
        else:
            raise CapsuleClosureHold("ambiguous Python package module identities")
    return by_path, module_map


def _import_record(
    source: ClosureSource, requested: str, *,
    target: ClosureSource | None, level: int, line: int,
    invalid: bool = False,
) -> ClosureImport:
    kind = (
        "invalid-relative-level" if invalid
        else "unverified-external-or-unselected" if target is None
        else "linked-selected-original" if target.kind == "selected-original"
        else "linked-review-change"
    )
    return ClosureImport(
        source_path=source.path, source_sha256=source.sha256,
        source_kind=source.kind,
        import_sha256=_hash(requested.encode("utf-8", "strict")),
        target_path=target.path if target is not None and not invalid else None,
        target_sha256=target.sha256 if target is not None and not invalid else None,
        target_kind=target.kind if target is not None and not invalid else None,
        level=level, line=line, status=kind,
    )


def _edges(
    selected: ClosureSource, modules: dict[str, ClosureSource],
) -> tuple[list[ClosureImport], int]:
    try:
        raw = selected.raw.decode("utf-8", "strict")
        tree = ast.parse(raw, filename=selected.path, mode="exec", type_comments=True)
    except (SyntaxError, UnicodeError, ValueError, RecursionError, MemoryError) as exc:
        raise CapsuleClosureHold(
            "selected original or reviewed Python source is not parseable",
        ) from exc
    result: list[ClosureImport] = []
    nodes = 0
    for node in ast.walk(tree):
        nodes += 1
        if nodes > MAX_NODES_PER_FILE:
            raise CapsuleClosureHold("Python AST node ceiling reached")
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.append(_import_record(
                    selected, alias.name, target=modules.get(alias.name),
                    level=0, line=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom):
            parent = _parent_package(selected.path)
            level = node.level
            invalid = level > len(parent) or level > 32
            if invalid:
                result.append(_import_record(
                    selected, "invalid-relative-" + str(level),
                    target=None, level=min(level, 32), line=node.lineno,
                    invalid=True,
                ))
                continue
            base = (
                ".".join((*parent[:len(parent) - level + 1],
                           *(node.module.split(".") if node.module else ())))
                if level else (node.module or "")
            )
            for alias in node.names:
                candidate = base + "." + alias.name if base else alias.name
                target = (
                    modules.get(candidate) or modules.get(base)
                )
                result.append(_import_record(
                    selected, candidate if candidate in modules else base or candidate,
                    target=target, level=level, line=node.lineno,
                ))
        if len(result) > MAX_IMPORTS_PER_FILE:
            raise CapsuleClosureHold("one selected file has too many Python imports")
    return result, nodes


def _cycles(
    python_paths: set[str], links: tuple[ClosureImport, ...],
) -> tuple[tuple[str, ...], ...]:
    edges = {path: set() for path in python_paths}
    for item in links:
        if item.target_path in python_paths and item.status.startswith("linked-"):
            edges[item.source_path].add(item.target_path)
    visiting: set[str] = set()
    seen: set[str] = set()
    path: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(item: str) -> None:
        if item in visiting:
            index = path.index(item)
            cycles.add(tuple(sorted(set(path[index:]))))
            return
        if item in seen:
            return
        visiting.add(item)
        path.append(item)
        for target in sorted(edges[item]):
            visit(target)
        path.pop()
        visiting.remove(item)
        seen.add(item)

    for name in sorted(edges):
        visit(name)
    if len(cycles) > MAX_CYCLES:
        raise CapsuleClosureHold("unbounded Python source import cycles")
    return tuple(sorted(cycles))


def analyze_capsule_source_closure(
    sources: tuple[ClosureSource, ...], *,
    source_manifest_sha256: str,
    source_patch_sha256: str,
) -> CapsuleClosure:
    """Pure bounded AST source graph from exact approved bytes (no file I/O)."""
    if not _sha(source_manifest_sha256) or not _sha(source_patch_sha256):
        raise CapsuleClosureHold("original exact reviewed source hashes required")
    _, modules = _source_set(sources)
    ordered = tuple(sorted(sources, key=lambda x: (x.path.casefold(), x.path)))
    python = tuple(item for item in ordered if item.python)
    if len(python) > MAX_PYTHON_FILES:
        raise CapsuleClosureHold("selected source Python count exceeded")
    source_digest = _hash(_canonical({
        "schema": SCHEMA,
        "source_manifest_sha256": source_manifest_sha256,
        "source_patch_sha256": source_patch_sha256,
        "sources": [
            {"path": x.path, "kind": x.kind, "sha256": x.sha256}
            for x in ordered
        ],
    }))
    links: list[ClosureImport] = []
    nodes = 0
    for entry in python:
        new_links, seen = _edges(entry, modules)
        nodes += seen
        if nodes > MAX_TOTAL_NODES:
            raise CapsuleClosureHold("selected Python AST aggregate ceiling reached")
        links.extend(new_links)
        if len(links) > MAX_TOTAL_IMPORTS:
            raise CapsuleClosureHold("selected Python import aggregate ceiling reached")
    linked = tuple(links)
    cycles = _cycles({x.path for x in python}, linked)
    status = (
        "no-selected-python" if not python
        else "invalid-relative-held" if any(
            x.status == "invalid-relative-level" for x in linked
        )
        else "partially-unverified-python" if any(
            x.status == "unverified-external-or-unselected" for x in linked
        )
        else "linked-selected-python"
    )
    core = {
        "schema": SCHEMA,
        "source_manifest_sha256": source_manifest_sha256,
        "source_patch_sha256": source_patch_sha256,
        "sources_sha256": source_digest,
        "python_count": len(python),
        "ast_nodes": nodes,
        "import_links": [x.public() for x in linked],
        "cycles": [list(x) for x in cycles],
    }
    report = CapsuleClosure(
        source_manifest_sha256=source_manifest_sha256,
        source_patch_sha256=source_patch_sha256,
        sources_sha256=source_digest,
        graph_sha256=_hash(_canonical(core)),
        python_count=len(python),
        ast_nodes=nodes,
        import_links=linked,
        cycles=cycles,
        status=status,
    )
    if not report.permits_inert_capsule:
        raise CapsuleClosureHold(
            "selected source contains impossible relative import; cannot claim capsule",
        )
    return report


__all__ = [
    "SCHEMA", "CapsuleClosureHold", "ClosureSource",
    "ClosureImport", "CapsuleClosure", "analyze_capsule_source_closure",
]
