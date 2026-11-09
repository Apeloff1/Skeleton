#!/usr/bin/env python3
"""Fail-closed ranked inventory of trust-boundary regression candidates.

Issue #969 Seed 08 (``reserve-S020-security-priority``) ranks trust-boundary
surfaces by *proven reachability* from HTTP, CLI, workflow, or other
entrypoints. Unknown or unreadable inputs fail closed. The scanner never
guesses CVSS/severity and never inflates ranking with an unevidenced score.

This inventory is not the capability matrix (S019), not the hidden-network
build audit (S026), and not a SAST/process-safety replacement. It only
answers: which trust-boundary candidates can actually be hit, and in what
exclusive reachability order?

Stdlib only. Do not import ``skeleton`` (that package pulls pydantic).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

TASK_ID = "reserve-S020-security-priority"
CONFLICT_DOMAIN = "security.readonly.regression_priority"
INVENTORY_VERSION = 1
FINDING_PREFIX = "S020-SEC-PRI"
SEVERITY_POLICY = "unscored"

REPO_ROOT = Path(__file__).resolve().parents[1]

REACHABILITY_CLASSES = (
    "reachable_http",
    "reachable_cli",
    "reachable_workflow",
    "reachable_entrypoint",
    "unreachable",
    "unknown",
)
REACHABILITY_SET = frozenset(REACHABILITY_CLASSES)

# Exclusive rank: one class per candidate. Lower rank is higher priority.
# ``unknown`` is not a backlog rank — it fails closed.
RANK_BY_CLASS: dict[str, int] = {
    "reachable_http": 0,
    "reachable_cli": 1,
    "reachable_workflow": 2,
    "reachable_entrypoint": 3,
    "unreachable": 4,
}

SCAN_ROOTS = (
    "skeleton",
    "backend",
    "scripts",
    "core",
    ".github/workflows",
)
SCAN_FILES = ("deploy.py",)

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".next",
        ".expo",
        "satellites",
        "branch-snapshots",
        "tests",
        "testing",
        "testdata",
        "legacy_root",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "htmlcov",
    }
)

HTTP_ORIGIN_NAMES = frozenset(
    {
        "APIRouter",
        "FastAPI",
        "Flask",
        "APIRoute",
    }
)
HTTP_DECORATOR_ATTRS = frozenset(
    {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
        "websocket",
        "api_route",
        "route",
        "middleware",
        "exception_handler",
        "on_event",
    }
)
CLI_TYPE_NAMES = frozenset({"ArgumentParser", "Typer", "Command"})
CLI_DECORATOR_ATTRS = frozenset({"command", "group", "callback"})
CLI_MODULES = frozenset({"argparse", "click", "typer"})
SENSITIVE_CALLS = frozenset(
    {
        "pickle.load",
        "pickle.loads",
        "_pickle.load",
        "_pickle.loads",
        "yaml.load",
        "yaml.unsafe_load",
        "yaml.unsafe_load_all",
        "marshal.loads",
        "marshal.load",
        "eval",
        "exec",
    }
)
WORKFLOW_PY_PATH_RE = re.compile(
    r"\b((?:scripts|backend|skeleton|core)/[A-Za-z0-9_./-]+\.py)\b"
)
WORKFLOW_MODULE_RE = re.compile(
    r"\bpython(?:3)?\s+-m\s+(skeleton(?:\.[A-Za-z0-9_]+)*)\b"
)
CONSOLE_SCRIPT_RE = re.compile(
    r"^\s*[\"']?([A-Za-z0-9_.-]+)[\"']?\s*=\s*[\"']([A-Za-z0-9_.]+)\s*:\s*[A-Za-z0-9_]+[\"']\s*$",
    re.MULTILINE,
)


class UnknownReachabilityError(RuntimeError):
    """Raised when reachability cannot be proved and must fail closed."""


class SecurityPriorityScanError(RuntimeError):
    """Raised when the scanner cannot prove complete discovery."""


@dataclass(frozen=True, slots=True)
class InventoryItem:
    """One ranked trust-boundary candidate. Severity is never guessed."""

    item_id: str
    path: str
    reachability: str
    rank: int | None
    evidence: tuple[str, ...]
    kind: str
    severity: None = None
    severity_claimed: bool = False
    notes: str = ""


@dataclass
class _FileFacts:
    relative: str
    readable: bool = True
    parse_error: str | None = None
    http_markers: tuple[str, ...] = ()
    cli_markers: tuple[str, ...] = ()
    entrypoint_markers: tuple[str, ...] = ()
    sensitive_markers: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    is_workflow: bool = False
    workflow_py_refs: tuple[str, ...] = ()
    workflow_modules: tuple[str, ...] = ()


@dataclass
class InventoryReport:
    """Deterministic ranked backlog. Unknown items fail closed."""

    task_key: str = TASK_ID
    conflict_domain: str = CONFLICT_DOMAIN
    inventory_version: int = INVENTORY_VERSION
    finding_prefix: str = FINDING_PREFIX
    severity_policy: str = SEVERITY_POLICY
    items: list[InventoryItem] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def ranked_items(self) -> list[InventoryItem]:
        return [item for item in self.items if item.reachability != "unknown"]


def exclusive_reachability(evidence_kinds: Iterable[str]) -> str:
    """Return exactly one reachability class from proven evidence kinds.

    ``unknown`` dominates: if discovery failed, the scanner must not guess a
    reachable class. Otherwise the highest-priority proven class wins.
    """

    kinds = {kind for kind in evidence_kinds if kind}
    unknown = kinds - REACHABILITY_SET
    if unknown:
        return "unknown"
    if "unknown" in kinds:
        return "unknown"
    for class_name in REACHABILITY_CLASSES:
        if class_name == "unknown" or class_name == "unreachable":
            continue
        if class_name in kinds:
            return class_name
    return "unreachable"


def rank_for_class(reachability: str) -> int | None:
    """Backlog rank, or ``None`` when the class must fail closed."""

    if reachability == "unknown":
        return None
    if reachability not in RANK_BY_CLASS:
        return None
    return RANK_BY_CLASS[reachability]


def ranking_key(item: InventoryItem) -> tuple[int, str, str]:
    """Sort exclusively by reachability rank, then stable path. Severity is ignored."""

    rank = item.rank if item.rank is not None else 10**6
    return (rank, item.path, item.item_id)


def _display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_skipped_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.startswith(".")


def _iter_scan_paths(root: Path) -> Iterator[Path]:
    """Yield regular files under scan roots without following symlinks."""

    pending: list[Path] = []
    for relative in SCAN_ROOTS:
        candidate = root / relative
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SecurityPriorityScanError(
                f"{FINDING_PREFIX}: root metadata failure: {type(exc).__name__}:{relative}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            continue
        if stat.S_ISDIR(metadata.st_mode):
            pending.append(candidate)
            continue
        if stat.S_ISREG(metadata.st_mode):
            yield candidate

    for relative in SCAN_FILES:
        candidate = root / relative
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SecurityPriorityScanError(
                f"{FINDING_PREFIX}: file metadata failure: {type(exc).__name__}:{relative}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            continue
        if stat.S_ISREG(metadata.st_mode):
            yield candidate

    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise SecurityPriorityScanError(
                f"{FINDING_PREFIX}: traversal failure: {type(exc).__name__}:"
                f"{_display(directory, root)}"
            ) from exc
        for entry in entries:
            name = entry.name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not _is_skipped_dir(name):
                        pending.append(Path(entry.path))
                    continue
                if entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
            except OSError as exc:
                raise SecurityPriorityScanError(
                    f"{FINDING_PREFIX}: entry metadata failure: {type(exc).__name__}:"
                    f"{_display(Path(entry.path), root)}"
                ) from exc


def _dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _decorator_attr(node: ast.AST) -> str | None:
    target = node
    if isinstance(node, ast.Call):
        target = node.func
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return None


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left = test.left
    right = test.comparators[0]
    names = {getattr(left, "id", None), getattr(right, "id", None)}
    constants: set[object] = set()
    for side in (left, right):
        if isinstance(side, ast.Constant):
            constants.add(side.value)
    return "__name__" in names and "__main__" in constants


def _package_parts(relative: str) -> list[str]:
    module = _module_name_for_path(relative)
    if not module:
        return []
    parts = module.split(".")
    if relative.endswith("/__init__.py") or relative == "__init__.py":
        return parts
    return parts[:-1]


def _module_name_for_path(relative: str) -> str | None:
    if not relative.endswith(".py"):
        return None
    parts = relative[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or any(not part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _path_for_module(module: str, index: Mapping[str, str]) -> str | None:
    if module in index:
        return index[module]
    return None


def _resolve_import_from(relative: str, node: ast.ImportFrom) -> list[str]:
    names: list[str] = []
    if node.level:
        package = _package_parts(relative)
        if node.level > len(package) + 1:
            return names
        base = package[: len(package) - node.level + 1]
        prefix = ".".join(base)
        if node.module:
            abs_module = f"{prefix}.{node.module}" if prefix else node.module
        else:
            abs_module = prefix
        if abs_module:
            names.append(abs_module)
            for item in node.names:
                if item.name != "*":
                    names.append(f"{abs_module}.{item.name}")
        return names
    if node.module:
        names.append(node.module)
        for item in node.names:
            if item.name != "*":
                names.append(f"{node.module}.{item.name}")
    return names


def _collect_python_facts(path: Path, relative: str) -> _FileFacts:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _FileFacts(
            relative=relative,
            readable=False,
            parse_error=f"{type(exc).__name__}",
        )
    except UnicodeDecodeError:
        return _FileFacts(
            relative=relative,
            readable=False,
            parse_error="UnicodeDecodeError",
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return _FileFacts(
            relative=relative,
            readable=True,
            parse_error=f"SyntaxError:{exc.lineno}",
        )

    http_markers: list[str] = []
    cli_markers: list[str] = []
    entrypoint_markers: list[str] = []
    sensitive_markers: list[str] = []
    imported_modules: list[str] = []
    aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                name = item.name
                aliases[item.asname or name.split(".", 1)[0]] = name
                imported_modules.append(name)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.extend(_resolve_import_from(relative, node))
            module_for_alias = node.module or ""
            if node.level and not module_for_alias:
                package = _package_parts(relative)
                if node.level <= len(package) + 1:
                    module_for_alias = ".".join(package[: len(package) - node.level + 1])
            for item in node.names:
                if item.name == "*":
                    continue
                if module_for_alias:
                    aliases[item.asname or item.name] = f"{module_for_alias}.{item.name}"
                else:
                    aliases[item.asname or item.name] = item.name
                if item.name in HTTP_ORIGIN_NAMES:
                    http_markers.append(f"import:{item.name}")
                if item.name in CLI_TYPE_NAMES:
                    cli_markers.append(f"import:{item.name}")

    def canonical(node: ast.AST) -> str | None:
        name = _dotted_name(node)
        if not name:
            return None
        root, dot, suffix = name.partition(".")
        replacement = aliases.get(root)
        if replacement is None:
            return name
        return replacement + (f".{suffix}" if dot else "")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = canonical(node.func)
            if name in SENSITIVE_CALLS or (name and name.split(".")[-1] in {"eval", "exec"} and name in SENSITIVE_CALLS):
                sensitive_markers.append(f"call:{name}:{node.lineno}")
            if name in {"eval", "exec"}:
                sensitive_markers.append(f"call:{name}:{node.lineno}")
            if name and name.rsplit(".", 1)[-1] in HTTP_ORIGIN_NAMES:
                http_markers.append(f"call:{name.rsplit('.', 1)[-1]}")
            if name and name.rsplit(".", 1)[-1] in CLI_TYPE_NAMES:
                cli_markers.append(f"call:{name.rsplit('.', 1)[-1]}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                attr = _decorator_attr(decorator)
                if attr in HTTP_DECORATOR_ATTRS:
                    http_markers.append(f"decorator:{attr}:{node.name}")
                if attr in CLI_DECORATOR_ATTRS:
                    func_name = canonical(decorator if not isinstance(decorator, ast.Call) else decorator.func)
                    if func_name and func_name.split(".", 1)[0] in CLI_MODULES:
                        cli_markers.append(f"decorator:{attr}:{node.name}")
                    elif attr in {"command", "group"} and func_name and "click" in func_name:
                        cli_markers.append(f"decorator:{attr}:{node.name}")
        if isinstance(node, ast.If) and _is_main_guard(node):
            entrypoint_markers.append(f"main_guard:{node.lineno}")

    if relative.endswith("/__main__.py") or relative == "__main__.py":
        entrypoint_markers.append("dunder_main_module")

    return _FileFacts(
        relative=relative,
        http_markers=tuple(sorted(set(http_markers))),
        cli_markers=tuple(sorted(set(cli_markers))),
        entrypoint_markers=tuple(sorted(set(entrypoint_markers))),
        sensitive_markers=tuple(sorted(set(sensitive_markers))),
        imports=tuple(sorted(set(imported_modules))),
    )


def _collect_workflow_facts(path: Path, relative: str) -> _FileFacts:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _FileFacts(
            relative=relative,
            readable=False,
            is_workflow=True,
            parse_error=f"{type(exc).__name__}",
        )
    except UnicodeDecodeError:
        return _FileFacts(
            relative=relative,
            readable=False,
            is_workflow=True,
            parse_error="UnicodeDecodeError",
        )
    py_refs = tuple(sorted(set(WORKFLOW_PY_PATH_RE.findall(text))))
    modules = tuple(sorted(set(WORKFLOW_MODULE_RE.findall(text))))
    return _FileFacts(
        relative=relative,
        is_workflow=True,
        workflow_py_refs=py_refs,
        workflow_modules=modules,
        entrypoint_markers=("workflow_file",),
    )


def _console_script_modules(root: Path) -> tuple[str, ...]:
    modules: list[str] = []
    for relative in ("pyproject.toml", "setup.cfg"):
        path = root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in CONSOLE_SCRIPT_RE.finditer(text):
            modules.append(match.group(2))
    return tuple(sorted(set(modules)))


def _is_candidate(facts: _FileFacts) -> bool:
    if facts.parse_error or not facts.readable:
        return True
    if facts.is_workflow:
        return True
    return bool(
        facts.http_markers
        or facts.cli_markers
        or facts.entrypoint_markers
        or facts.sensitive_markers
    )


def _evidence_for_file(
    facts: _FileFacts,
    *,
    http_hits: Sequence[str],
    cli_hits: Sequence[str],
    workflow_hits: Sequence[str],
    entrypoint_hits: Sequence[str],
) -> list[str]:
    evidence: list[str] = []
    evidence.extend(f"http:{marker}" for marker in facts.http_markers)
    evidence.extend(f"cli:{marker}" for marker in facts.cli_markers)
    evidence.extend(f"entrypoint:{marker}" for marker in facts.entrypoint_markers)
    evidence.extend(f"sensitive:{marker}" for marker in facts.sensitive_markers)
    if facts.is_workflow:
        evidence.append(f"workflow:self:{facts.relative}")
        evidence.extend(f"workflow:py:{ref}" for ref in facts.workflow_py_refs)
        evidence.extend(f"workflow:module:{mod}" for mod in facts.workflow_modules)
    evidence.extend(http_hits)
    evidence.extend(cli_hits)
    evidence.extend(workflow_hits)
    evidence.extend(entrypoint_hits)
    return sorted(set(evidence))


def _kinds_from_evidence(evidence: Sequence[str], *, unknown: bool) -> set[str]:
    if unknown:
        return {"unknown"}
    kinds: set[str] = set()
    for item in evidence:
        if item.startswith("http:") or item.startswith("reach:http:"):
            kinds.add("reachable_http")
        elif item.startswith("cli:") or item.startswith("reach:cli:"):
            kinds.add("reachable_cli")
        elif item.startswith("workflow:") or item.startswith("reach:workflow:"):
            kinds.add("reachable_workflow")
        elif item.startswith("entrypoint:") or item.startswith("reach:entrypoint:"):
            kinds.add("reachable_entrypoint")
    return kinds


def _build_import_edges(
    facts_by_path: Mapping[str, _FileFacts],
    module_index: Mapping[str, str],
) -> dict[str, set[str]]:
    """Map importer path -> imported scanned paths."""

    edges: dict[str, set[str]] = {path: set() for path in facts_by_path}
    for relative, facts in facts_by_path.items():
        if facts.is_workflow or facts.parse_error:
            continue
        for module in facts.imports:
            target = _path_for_module(module, module_index)
            if target is None:
                # Allow prefix imports: ``from skeleton.api import routes``
                # already records module ``skeleton.api``; also try children
                # recorded via alias mapping above.
                continue
            if target in edges and target != relative:
                edges[relative].add(target)
            # Importer reaches the imported module.
        # Reverse later for reachability from entrypoints.
    return edges


def _reachable_from(origins: Iterable[str], forward: Mapping[str, set[str]]) -> set[str]:
    """Files reachable *from* origins following imports (origin imports X => X reachable)."""

    seen: set[str] = set()
    stack = list(origins)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for imported in forward.get(current, ()):
            if imported not in seen:
                stack.append(imported)
    return seen


def scan_repo(root: Path | None = None) -> InventoryReport:
    """Scan ``root`` and return a ranked, fail-closed inventory report."""

    repo = root if root is not None else REPO_ROOT
    violations: list[str] = []
    try:
        paths = list(_iter_scan_paths(repo))
    except SecurityPriorityScanError as exc:
        report = InventoryReport(violations=[str(exc)])
        return report

    facts_by_path: dict[str, _FileFacts] = {}
    for path in paths:
        relative = _display(path, repo)
        suffix = path.suffix.lower()
        under_workflows = "/.github/workflows/" in f"/{relative}" or relative.startswith(
            ".github/workflows/"
        )
        if under_workflows and suffix in {".yml", ".yaml"}:
            facts_by_path[relative] = _collect_workflow_facts(path, relative)
            continue
        if suffix != ".py":
            continue
        facts_by_path[relative] = _collect_python_facts(path, relative)

    module_index: dict[str, str] = {}
    for relative, facts in facts_by_path.items():
        if facts.is_workflow:
            continue
        module = _module_name_for_path(relative)
        if module:
            module_index[module] = relative

    for module in _console_script_modules(repo):
        target = _path_for_module(module, module_index)
        if target and target in facts_by_path:
            facts = facts_by_path[target]
            extra = facts.cli_markers + ("console_script:" + module,)
            facts_by_path[target] = _FileFacts(
                relative=facts.relative,
                readable=facts.readable,
                parse_error=facts.parse_error,
                http_markers=facts.http_markers,
                cli_markers=tuple(sorted(set(extra))),
                entrypoint_markers=facts.entrypoint_markers,
                sensitive_markers=facts.sensitive_markers,
                imports=facts.imports,
            )

    forward = _build_import_edges(facts_by_path, module_index)

    http_origins = [
        path
        for path, facts in facts_by_path.items()
        if facts.http_markers and not facts.parse_error
    ]
    cli_origins = [
        path
        for path, facts in facts_by_path.items()
        if facts.cli_markers and not facts.parse_error
    ]
    entry_origins = [
        path
        for path, facts in facts_by_path.items()
        if facts.entrypoint_markers and not facts.parse_error and not facts.is_workflow
    ]
    workflow_script_hits: dict[str, list[str]] = {path: [] for path in facts_by_path}
    for path, facts in facts_by_path.items():
        if not facts.is_workflow or facts.parse_error:
            continue
        for ref in facts.workflow_py_refs:
            if ref in workflow_script_hits:
                workflow_script_hits[ref].append(f"reach:workflow:{path}")
        for module in facts.workflow_modules:
            target = _path_for_module(module, module_index)
            if target is None and module:
                # python -m skeleton -> skeleton/__main__.py
                target = _path_for_module(f"{module}.__main__", module_index) or _path_for_module(
                    module, module_index
                )
            if target in workflow_script_hits:
                workflow_script_hits[target].append(f"reach:workflow:{path}")

    workflow_origins = [
        path for path, hits in workflow_script_hits.items() if hits
    ] + [
        path
        for path, facts in facts_by_path.items()
        if facts.is_workflow and not facts.parse_error
    ]

    http_reach = _reachable_from(http_origins, forward)
    cli_reach = _reachable_from(cli_origins, forward)
    workflow_reach = _reachable_from(workflow_origins, forward)
    entry_reach = _reachable_from(entry_origins, forward)

    raw_items: list[InventoryItem] = []
    for relative, facts in facts_by_path.items():
        unknown = (not facts.readable) or bool(facts.parse_error)
        if not _is_candidate(facts):
            continue

        http_hits = []
        if relative in http_reach:
            http_hits.append("reach:http:self" if facts.http_markers else "reach:http:import_graph")
        cli_hits = []
        if relative in cli_reach:
            cli_hits.append("reach:cli:self" if facts.cli_markers else "reach:cli:import_graph")
        entry_hits = []
        if relative in entry_reach:
            entry_hits.append(
                "reach:entrypoint:self" if facts.entrypoint_markers else "reach:entrypoint:import_graph"
            )
        wf_hits = list(workflow_script_hits.get(relative, ()))
        if relative in workflow_reach and facts.is_workflow:
            wf_hits.append("reach:workflow:self")
        elif relative in workflow_reach and not wf_hits:
            wf_hits.append("reach:workflow:import_graph")

        evidence = _evidence_for_file(
            facts,
            http_hits=http_hits,
            cli_hits=cli_hits,
            workflow_hits=wf_hits,
            entrypoint_hits=entry_hits,
        )
        kinds = _kinds_from_evidence(evidence, unknown=unknown)
        reachability = exclusive_reachability(kinds)
        if unknown:
            reachability = "unknown"
            violations.append(
                f"{FINDING_PREFIX}: unknown class fails closed: {relative}"
                + (f" ({facts.parse_error})" if facts.parse_error else "")
            )
        rank = rank_for_class(reachability)
        kind = "workflow" if facts.is_workflow else "python"
        raw_items.append(
            InventoryItem(
                item_id="",
                path=relative,
                reachability=reachability,
                rank=rank,
                evidence=tuple(evidence),
                kind=kind,
                severity=None,
                severity_claimed=False,
                notes="" if not facts.parse_error else f"unreadable:{facts.parse_error}",
            )
        )

    raw_items.sort(key=lambda item: ranking_key(item))
    items: list[InventoryItem] = []
    for index, item in enumerate(raw_items, start=1):
        items.append(
            InventoryItem(
                item_id=f"{FINDING_PREFIX}-{index:04d}",
                path=item.path,
                reachability=item.reachability,
                rank=item.rank,
                evidence=item.evidence,
                kind=item.kind,
                severity=None,
                severity_claimed=False,
                notes=item.notes,
            )
        )

    seen_paths: dict[str, int] = {}
    for item in items:
        seen_paths[item.path] = seen_paths.get(item.path, 0) + 1
        extra = item_violations(item)
        violations.extend(extra)
    for path, count in seen_paths.items():
        if count > 1:
            violations.append(f"{FINDING_PREFIX}: duplicate path fails closed: {path}")

    violations = sorted(set(violations))
    return InventoryReport(items=items, violations=violations)


def item_violations(item: InventoryItem) -> list[str]:
    issues: list[str] = []
    prefix = f"{FINDING_PREFIX}:{item.path}: "
    if item.reachability not in REACHABILITY_SET:
        issues.append(prefix + f"unknown class fails closed: {item.reachability}")
    if item.reachability == "unknown":
        issues.append(prefix + "unknown class fails closed")
    if item.severity_claimed or item.severity is not None:
        issues.append(prefix + "severity claimed without evidence")
    if item.rank is None and item.reachability != "unknown":
        issues.append(prefix + f"unranked class fails closed: {item.reachability}")
    if item.reachability != "unknown" and item.reachability != "unreachable":
        if not item.evidence:
            issues.append(prefix + "reachable class missing reachability evidence")
    return issues


def collect_violations(
    root: Path | None = None,
    *,
    report: InventoryReport | None = None,
) -> list[str]:
    """Return fail-closed defects. Empty means the inventory is closed."""

    current = report if report is not None else scan_repo(root)
    return list(current.violations)


def assert_inventory_closed(root: Path | None = None) -> None:
    issues = collect_violations(root)
    if issues:
        raise UnknownReachabilityError("; ".join(issues))


def report_to_dict(report: InventoryReport) -> dict[str, object]:
    return {
        "task_key": report.task_key,
        "conflict_domain": report.conflict_domain,
        "inventory_version": report.inventory_version,
        "finding_prefix": report.finding_prefix,
        "severity_policy": report.severity_policy,
        "items": [
            {
                "id": item.item_id,
                "path": item.path,
                "reachability": item.reachability,
                "rank": item.rank,
                "kind": item.kind,
                "evidence": list(item.evidence),
                "severity": item.severity,
                "severity_claimed": item.severity_claimed,
                "notes": item.notes,
            }
            for item in report.items
        ],
        "violations": list(report.violations),
    }


def render_report(report: InventoryReport) -> str:
    payload = report_to_dict(report)
    return json.dumps(payload, indent=2, sort_keys=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root to scan (default: this checkout)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the deterministic JSON report instead of the TSV backlog",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = scan_repo(args.root)
    if args.json:
        print(render_report(report))
    else:
        print(
            f"{FINDING_PREFIX}\t{TASK_ID}\t{CONFLICT_DOMAIN}\t"
            f"severity_policy={SEVERITY_POLICY}"
        )
        for item in report.items:
            rank = "" if item.rank is None else str(item.rank)
            print(
                f"{item.item_id}\t{item.reachability}\t{rank}\t{item.path}\t"
                f"{item.kind}\tseverity=unscored"
            )
        if report.violations:
            print("VIOLATIONS:", file=sys.stderr)
            for issue in report.violations:
                print(f"- {issue}", file=sys.stderr)
    return 1 if report.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
