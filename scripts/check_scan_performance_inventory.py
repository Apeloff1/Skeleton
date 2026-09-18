#!/usr/bin/env python3
"""Fail-closed structural inventory of repository gate-scanner performance shapes.

Issue #969 Seed 11 (``reserve-S029-scan-performance-audit``) classifies Python
gate scanners under ``scripts/`` and ``backend/scripts/`` using AST evidence
only. It reports repeated full-tree walks, git subprocesses inside per-item
loops, and nested O(n^2) walks. Unknown or unreadable files fail closed.

This inventory does not rewrite scanners, does not invent wall-clock timings
for the live repository, and does not own source-root, compat-shim, fanout,
capability, property-test, or durable-state inventories.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


TASK_KEY = "reserve-S029-scan-performance-audit"
CONFLICT_DOMAIN = "repo.readonly.scan_performance"
INVENTORY_VERSION = 1
EVIDENCE_KIND = "structural"

HOTSPOT_CLASSES = (
    "quadratic_nested_walk",
    "git_subprocess_per_file",
    "repeated_full_tree_walk",
)
LINEAR_CLASS = "linear_single_pass"
UNKNOWN_CLASS = "unknown"
CLASSIFICATIONS = (*HOTSPOT_CLASSES, LINEAR_CLASS, UNKNOWN_CLASS)

SCAN_ROOTS = ("scripts", "backend/scripts")
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "legacy_root",
        "satellites",
        "branch-snapshots",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)
TRACKED_MODULES = frozenset({"os", "pathlib", "glob", "subprocess", "pathlib.Path"})
SUBPROCESS_CALLS = frozenset({"run", "call", "check_call", "check_output", "Popen"})
SCANDIR_NAMES = frozenset({"os.scandir"})
GIT_LITERAL = "git"

REPO_ROOT = Path(__file__).resolve().parents[1]


class ScanPerformanceInventoryError(RuntimeError):
    """Raised when the inventory cannot classify a scanner fail-closed."""


@dataclass(frozen=True)
class ScannerRecord:
    """One classified gate-scanner Python file."""

    path: str
    classification: str
    evidence: tuple[str, ...]
    walk_sites: int
    git_in_loop_sites: int
    nested_walk_sites: int
    timing: None = None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        payload["timing"] = None
        return payload


def _display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> Iterator[ast.AST]:
    current = parents.get(node)
    while current is not None:
        yield current
        current = parents.get(current)


def _enclosing_function(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for ancestor in _ancestors(node, parents):
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ancestor
        if isinstance(ancestor, ast.Module):
            return None
    return None


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                if root in {"os", "pathlib", "glob", "subprocess"} or item.name in TRACKED_MODULES:
                    aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root not in {"os", "pathlib", "glob", "subprocess"}:
                continue
            for item in node.names:
                if item.name == "*":
                    continue
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def _canonical(node: ast.AST, aliases: dict[str, str]) -> str | None:
    name = _dotted(node)
    if not name:
        return None
    root, _dot, suffix = name.partition(".")
    resolved = aliases.get(root, root)
    if suffix:
        return f"{resolved}.{suffix}"
    return resolved


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _first_list_elt(node: ast.AST) -> ast.AST | None:
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Starred):
            return None
        return first
    return None


def _is_git_argv(node: ast.AST) -> bool:
    if _const_str(node) == GIT_LITERAL:
        return True
    first = _first_list_elt(node)
    return first is not None and _const_str(first) == GIT_LITERAL


def _glob_is_recursive(call: ast.Call) -> bool:
    if call.args:
        pattern = _const_str(call.args[0])
        if pattern is not None and "**" in pattern:
            return True
    for keyword in call.keywords:
        if keyword.arg == "recursive" and isinstance(keyword.value, ast.Constant):
            if keyword.value.value is True:
                return True
        if keyword.arg in {"pathname", "path"}:
            pattern = _const_str(keyword.value)
            if pattern is not None and "**" in pattern:
                return True
    return False


def _call_is_walk(call: ast.Call, aliases: dict[str, str]) -> bool:
    name = _canonical(call.func, aliases)
    if name in {"os.walk", "os.fwalk"}:
        return True
    if name in {"glob.glob", "glob.iglob"}:
        return _glob_is_recursive(call)
    if isinstance(call.func, ast.Attribute) and call.func.attr == "rglob":
        return True
    if isinstance(call.func, ast.Attribute) and call.func.attr == "glob":
        return _glob_is_recursive(call)
    return False


def _call_is_scandir(call: ast.Call, aliases: dict[str, str]) -> bool:
    return _canonical(call.func, aliases) in SCANDIR_NAMES or (
        isinstance(call.func, ast.Attribute) and call.func.attr == "scandir"
    )


def _call_is_subprocess(call: ast.Call, aliases: dict[str, str]) -> bool:
    name = _canonical(call.func, aliases)
    if name is None:
        return False
    if name in {f"subprocess.{method}" for method in SUBPROCESS_CALLS}:
        return True
    if isinstance(call.func, ast.Attribute) and call.func.attr in SUBPROCESS_CALLS:
        owner = _canonical(call.func.value, aliases)
        return owner == "subprocess"
    return False


def _subprocess_argv(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    for keyword in call.keywords:
        if keyword.arg in {"args", "cmd"}:
            return keyword.value
    return None


def _call_is_git_subprocess(call: ast.Call, aliases: dict[str, str]) -> bool:
    if not _call_is_subprocess(call, aliases):
        return False
    argv = _subprocess_argv(call)
    return argv is not None and _is_git_argv(argv)


def _opaque_dynamic(call: ast.Call, aliases: dict[str, str]) -> bool:
    func = call.func
    if isinstance(func, ast.Name) and func.id == "getattr":
        owner_node = call.args[0] if call.args else None
        attr_node = call.args[1] if len(call.args) > 1 else None
    elif isinstance(func, ast.Attribute) and func.attr == "getattr" and call.args:
        owner_node = call.args[0]
        attr_node = call.args[1] if len(call.args) > 1 else None
    else:
        return False
    if owner_node is None:
        return False
    owner = _canonical(owner_node, aliases)
    if owner not in {"os", "subprocess", "pathlib", "pathlib.Path", "glob"}:
        return False
    return _const_str(attr_node) is None if attr_node is not None else True


def _walk_root_expr(call: ast.Call) -> ast.AST | None:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in {"rglob", "glob"}:
        return func.value
    if call.args:
        return call.args[0]
    for keyword in call.keywords:
        if keyword.arg in {"top", "path", "root", "pathname"}:
            return keyword.value
    return None


def _root_key(expr: ast.AST | None) -> str:
    if expr is None:
        return "<unknown-root>"
    return ast.dump(expr, include_attributes=False)


def _iter_node(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.For):
        return node.iter
    if isinstance(node, ast.comprehension):
        return node.iter
    if isinstance(node, ast.While):
        return node.test
    return None


def _constant_collection(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(isinstance(elt, ast.Constant) for elt in node.elts)
    return False


def _name_bound_to_constants(
    name: str, function: ast.AST | None, tree: ast.AST
) -> bool:
    scope: ast.AST = function if function is not None else tree
    for child in ast.walk(scope):
        if isinstance(child, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in child.targets):
                if _constant_collection(child.value):
                    return True
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            if child.target.id == name and child.value is not None and _constant_collection(child.value):
                return True
    return False


def _is_trivial_iter(
    iter_node: ast.AST,
    aliases: dict[str, str],
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
    tree: ast.AST,
) -> bool:
    current = iter_node
    if isinstance(current, ast.Call):
        name = _canonical(current.func, aliases)
        if name in {"enumerate", "sorted", "list", "tuple", "reversed", "set"}:
            if current.args:
                current = current.args[0]
            else:
                return False
        elif name == "range":
            return True
        elif name == "zip":
            return all(_is_trivial_iter(arg, aliases, function, tree) for arg in current.args)
    if _constant_collection(current):
        return True
    if isinstance(current, ast.Name) and _name_bound_to_constants(current.id, function, tree):
        return True
    return False


def _in_scope(
    node: ast.AST,
    scope: ast.FunctionDef | ast.AsyncFunctionDef | ast.Module,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    enclosing = _enclosing_function(node, parents)
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return enclosing is scope
    return enclosing is None


def _is_under(node: ast.AST, root: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current: ast.AST | None = node
    while current is not None:
        if current is root:
            return True
        current = parents.get(current)
    return False


def _loop_ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    """Return loops whose *body* contains ``node``. Iterator expressions are excluded.

    ``for path in git_ls_files():`` must not count the listing subprocess as a
    per-item git call. Nested body calls still count.
    """
    loops: list[ast.AST] = []
    for ancestor in _ancestors(node, parents):
        if isinstance(ancestor, ast.For):
            if _is_under(node, ancestor.iter, parents):
                continue
            loops.append(ancestor)
        elif isinstance(ancestor, ast.comprehension):
            if _is_under(node, ancestor.iter, parents):
                continue
            loops.append(ancestor)
        elif isinstance(ancestor, ast.While):
            if _is_under(node, ancestor.test, parents):
                continue
            loops.append(ancestor)
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
            break
    return loops


def _target_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.update(_target_names(elt))
    return names


def _loop_target_names(loop: ast.AST) -> set[str]:
    if isinstance(loop, ast.For):
        return _target_names(loop.target)
    if isinstance(loop, ast.comprehension):
        return _target_names(loop.target)
    return set()


def _uses_name(node: ast.AST, names: set[str]) -> bool:
    if not names:
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in names:
            return True
    return False


class _ModuleAnalysis:
    def __init__(self, tree: ast.AST) -> None:
        self.tree = tree
        self.parents = _parents(tree)
        self.aliases = _import_aliases(tree)
        self.functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
        self.walk_functions: set[str] = set()
        self.git_functions: set[str] = set()
        self.custom_walkers: set[str] = set()
        self._summarize_functions()

    def _direct_walk(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for child in ast.walk(function):
            if isinstance(child, ast.Call) and _call_is_walk(child, self.aliases):
                return True
        return False

    def _direct_scandir_loop(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        has_scandir = False
        has_while_or_self = False
        for child in ast.walk(function):
            if isinstance(child, ast.Call) and _call_is_scandir(child, self.aliases):
                has_scandir = True
            if isinstance(child, ast.While):
                has_while_or_self = True
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == function.name
            ):
                has_while_or_self = True
        return has_scandir and has_while_or_self

    def _direct_git(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for child in ast.walk(function):
            if isinstance(child, ast.Call) and _call_is_git_subprocess(child, self.aliases):
                return True
        return False

    def _called_names(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        names: set[str] = set()
        for child in ast.walk(function):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                names.add(child.func.id)
        return names

    def _summarize_functions(self) -> None:
        for name, function in self.functions.items():
            if self._direct_walk(function) or self._direct_scandir_loop(function):
                self.walk_functions.add(name)
            if self._direct_scandir_loop(function):
                self.custom_walkers.add(name)
            if self._direct_git(function):
                self.git_functions.add(name)
        changed = True
        while changed:
            changed = False
            for name, function in self.functions.items():
                called = self._called_names(function)
                if name not in self.walk_functions and called & self.walk_functions:
                    self.walk_functions.add(name)
                    changed = True
                if name not in self.git_functions and called & self.git_functions:
                    self.git_functions.add(name)
                    changed = True

    def call_is_walk_site(self, call: ast.Call) -> bool:
        if _call_is_walk(call, self.aliases):
            return True
        if isinstance(call.func, ast.Name) and call.func.id in self.walk_functions:
            return True
        return False

    def call_is_git_site(self, call: ast.Call) -> bool:
        if _call_is_git_subprocess(call, self.aliases):
            return True
        if isinstance(call.func, ast.Name) and call.func.id in self.git_functions:
            return True
        return False

    def iter_is_walk(self, iter_node: ast.AST) -> bool:
        current = iter_node
        if isinstance(current, ast.Call):
            name = _canonical(current.func, self.aliases)
            if name in {"enumerate", "sorted", "list", "tuple", "reversed", "set"}:
                if not current.args:
                    return False
                current = current.args[0]
        if isinstance(current, ast.Call) and self.call_is_walk_site(current):
            return True
        return False

    def call_is_l0_walk(self, call: ast.Call) -> bool:
        if _call_is_walk(call, self.aliases):
            return True
        return isinstance(call.func, ast.Name) and call.func.id in self.custom_walkers

    def direct_l0_sites(
        self,
        function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Module,
        nested_walks: set[ast.Call],
    ) -> list[tuple[int, str]]:
        sites: list[tuple[int, str]] = []
        for child in ast.walk(function):
            if not isinstance(child, ast.Call) or child in nested_walks:
                continue
            if not _in_scope(child, function, self.parents):
                continue
            if not self.call_is_l0_walk(child):
                continue
            if _call_is_walk(child, self.aliases):
                key = _root_key(_walk_root_expr(child))
            else:
                arg_key = _root_key(child.args[0]) if child.args else "()"
                key = f"fn:{child.func.id}:{arg_key}"  # type: ignore[union-attr]
            sites.append((getattr(child, "lineno", 0), key))
        return sites

    def l0_functions(self, nested_walks: set[ast.Call]) -> dict[str, list[tuple[int, str]]]:
        mapping: dict[str, list[tuple[int, str]]] = {}
        for name, function in self.functions.items():
            sites = self.direct_l0_sites(function, nested_walks)
            if sites:
                mapping[name] = sites
        return mapping

    def name_bound_to_walk(
        self,
        name: str,
        function: ast.FunctionDef | ast.AsyncFunctionDef | None,
    ) -> bool:
        scope: ast.AST = function if function is not None else self.tree
        for child in ast.walk(scope):
            if isinstance(child, ast.Assign):
                if not any(isinstance(target, ast.Name) and target.id == name for target in child.targets):
                    continue
                value = child.value
                if isinstance(value, ast.Call) and self.iter_is_walk(value):
                    return True
                if isinstance(value, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
                    if value.generators and self.iter_is_walk(value.generators[0].iter):
                        return True
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                if child.target.id != name or child.value is None:
                    continue
                if isinstance(child.value, ast.Call) and self.iter_is_walk(child.value):
                    return True
        return False


def classify_source(source: str, filename: str = "<scanner>") -> ScannerRecord:
    """Classify one scanner from source text. Syntax errors are unknown."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        evidence = f"syntax error: {type(exc).__name__} at line {exc.lineno or 0}"
        return ScannerRecord(
            path=filename,
            classification=UNKNOWN_CLASS,
            evidence=(evidence,),
            walk_sites=0,
            git_in_loop_sites=0,
            nested_walk_sites=0,
        )

    analysis = _ModuleAnalysis(tree)
    walk_calls: list[ast.Call] = []
    git_loop_calls: list[ast.Call] = []
    nested_walk_calls: list[ast.Call] = []
    opaque = False
    nested_iteration_evidence: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _opaque_dynamic(node, analysis.aliases):
            opaque = True
        if analysis.call_is_walk_site(node):
            walk_calls.append(node)
            for loop in _loop_ancestors(node, analysis.parents):
                iter_node = _iter_node(loop)
                if iter_node is None:
                    continue
                if analysis.iter_is_walk(iter_node):
                    nested_walk_calls.append(node)
                    break
        if analysis.call_is_git_site(node):
            function = _enclosing_function(node, analysis.parents)
            for loop in _loop_ancestors(node, analysis.parents):
                iter_node = _iter_node(loop)
                if iter_node is None:
                    continue
                if _is_trivial_iter(iter_node, analysis.aliases, function, tree):
                    continue
                names = _loop_target_names(loop)
                if names and not _uses_name(node, names):
                    # Git helper called from a per-item loop even when the loop
                    # variable is passed through a wrapper still counts.
                    if not (
                        isinstance(node.func, ast.Name) and node.func.id in analysis.git_functions
                    ):
                        continue
                git_loop_calls.append(node)
                break

    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        inner_fors = [child for child in ast.walk(node) if isinstance(child, ast.For) and child is not node]
        if not inner_fors:
            continue
        function = _enclosing_function(node, analysis.parents)
        outer_iter = node.iter
        outer_is_walk = analysis.iter_is_walk(outer_iter) or (
            isinstance(outer_iter, ast.Name)
            and analysis.name_bound_to_walk(outer_iter.id, function)
        )
        if not outer_is_walk:
            continue
        for inner in inner_fors:
            inner_is_walk = analysis.iter_is_walk(inner.iter) or (
                isinstance(inner.iter, ast.Name)
                and (
                    analysis.name_bound_to_walk(inner.iter.id, function)
                    or (
                        isinstance(outer_iter, ast.Name)
                        and inner.iter.id == outer_iter.id
                    )
                )
            )
            if inner_is_walk:
                nested_iteration_evidence.append(
                    f"nested iteration at line {inner.lineno} inside walk loop at line {node.lineno}"
                )

    nested_walk_set = set(nested_walk_calls)
    l0_by_function = analysis.l0_functions(nested_walk_set)
    repeated_evidence: list[str] = []
    scopes: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.Module] = [
        *analysis.functions.values(),
        tree,
    ]
    for scope in scopes:
        sites = list(analysis.direct_l0_sites(scope, nested_walk_set))
        for child in ast.walk(scope):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Name):
                continue
            if not _in_scope(child, scope, analysis.parents):
                continue
            callee = child.func.id
            if callee not in l0_by_function:
                continue
            for _lineno, key in l0_by_function[callee]:
                sites.append((getattr(child, "lineno", 0), key))
        counts: dict[str, list[int]] = {}
        for lineno, key in sites:
            counts.setdefault(key, []).append(lineno)
        for key, lines in counts.items():
            unique_sites = sorted(set(lines))
            if len(unique_sites) >= 2:
                repeated_evidence.append(
                    "repeated full-tree walks of "
                    f"{key} at lines {', '.join(str(line) for line in unique_sites)}"
                )

    non_nested_walks = [call for call in walk_calls if call not in nested_walk_calls]

    evidence: list[str] = []
    classification = LINEAR_CLASS
    if nested_walk_calls or nested_iteration_evidence:
        classification = "quadratic_nested_walk"
        for call in nested_walk_calls:
            evidence.append(f"nested full-tree walk at line {call.lineno}")
        evidence.extend(nested_iteration_evidence)
    elif git_loop_calls:
        classification = "git_subprocess_per_file"
        for call in git_loop_calls:
            evidence.append(f"git subprocess inside per-item loop at line {call.lineno}")
    elif repeated_evidence:
        classification = "repeated_full_tree_walk"
        evidence.extend(repeated_evidence)
    elif opaque and not walk_calls and not git_loop_calls:
        classification = UNKNOWN_CLASS
        evidence.append("opaque dynamic os/subprocess/pathlib dispatch")
    else:
        if walk_calls:
            evidence.append(
                "single-pass or distinct-root traversal at lines "
                + ", ".join(str(call.lineno) for call in non_nested_walks)
            )
        else:
            evidence.append("no full-tree walk or git-per-item subprocess proved")

    # Deduplicate evidence while preserving order.
    seen_ev: set[str] = set()
    ordered: list[str] = []
    for item in evidence:
        if item not in seen_ev:
            seen_ev.add(item)
            ordered.append(item)

    return ScannerRecord(
        path=filename,
        classification=classification,
        evidence=tuple(ordered),
        walk_sites=len(walk_calls),
        git_in_loop_sites=len(git_loop_calls),
        nested_walk_sites=len(nested_walk_calls) + len(nested_iteration_evidence),
    )


def classify_path(path: Path, *, display: str | None = None) -> ScannerRecord:
    label = display if display is not None else path.as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ScannerRecord(
            path=label,
            classification=UNKNOWN_CLASS,
            evidence=(f"unreadable: {type(exc).__name__}",),
            walk_sites=0,
            git_in_loop_sites=0,
            nested_walk_sites=0,
        )
    record = classify_source(source, filename=label)
    return record


def _walk_error(exc: OSError) -> None:
    raise ScanPerformanceInventoryError(f"scanner traversal failure: {type(exc).__name__}") from None


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield Python files without following symlinks or hiding traversal errors."""
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise ScanPerformanceInventoryError(f"scan root metadata failure: {type(exc).__name__}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ScanPerformanceInventoryError("scan root must not be a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ScanPerformanceInventoryError("scan root is not a directory")

    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            _walk_error(exc)
            return
        child_dirs: list[Path] = []
        python_files: list[Path] = []
        for entry in sorted(entries, key=lambda item: item.name):
            if entry.name in SKIP_DIRS:
                continue
            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    child_dirs.append(path)
                elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                    python_files.append(path)
            except OSError as exc:
                raise ScanPerformanceInventoryError(
                    f"{path}: scanner metadata failure: {type(exc).__name__}"
                ) from None
        yield from python_files
        stack.extend(reversed(child_dirs))


def scan_roots_for(repo_root: Path) -> list[Path]:
    roots: list[Path] = []
    missing: list[str] = []
    for relative in SCAN_ROOTS:
        path = repo_root / relative
        if not path.exists():
            missing.append(relative)
            continue
        roots.append(path)
    if missing:
        raise ScanPerformanceInventoryError(
            "required scan root missing: " + ", ".join(missing)
        )
    return roots


def collect_records(repo_root: Path) -> list[ScannerRecord]:
    records: list[ScannerRecord] = []
    seen: set[Path] = set()
    for root in scan_roots_for(repo_root):
        for path in iter_python_files(root):
            absolute = path.resolve()
            if absolute in seen:
                continue
            seen.add(absolute)
            records.append(classify_path(path, display=_display(path, repo_root)))
    records.sort(key=lambda record: record.path)
    return records


def unknown_records(records: Iterable[ScannerRecord]) -> list[ScannerRecord]:
    return [record for record in records if record.classification == UNKNOWN_CLASS]


def candidate_records(records: Iterable[ScannerRecord]) -> list[ScannerRecord]:
    return [record for record in records if record.classification in HOTSPOT_CLASSES]


def inventory_report(repo_root: Path) -> dict[str, object]:
    records = collect_records(repo_root)
    if not records:
        raise ScanPerformanceInventoryError("scanner coverage failure: zero Python files classified")
    payload = {
        "task_key": TASK_KEY,
        "conflict_domain": CONFLICT_DOMAIN,
        "inventory_version": INVENTORY_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "scanned_roots": list(SCAN_ROOTS),
        "file_count": len(records),
        "candidate_count": len(candidate_records(records)),
        "unknown_count": len(unknown_records(records)),
        "classifications": CLASSIFICATIONS,
        "records": [record.as_dict() for record in records],
        "candidates": [record.as_dict() for record in candidate_records(records)],
    }
    return payload


def report_from_records(records: list[ScannerRecord]) -> dict[str, object]:
    if not records:
        raise ScanPerformanceInventoryError("scanner coverage failure: zero Python files classified")
    return {
        "task_key": TASK_KEY,
        "conflict_domain": CONFLICT_DOMAIN,
        "inventory_version": INVENTORY_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "scanned_roots": list(SCAN_ROOTS),
        "file_count": len(records),
        "candidate_count": len(candidate_records(records)),
        "unknown_count": len(unknown_records(records)),
        "classifications": CLASSIFICATIONS,
        "records": [record.as_dict() for record in records],
        "candidates": [record.as_dict() for record in candidate_records(records)],
    }


def inventory_report(repo_root: Path) -> dict[str, object]:
    return report_from_records(collect_records(repo_root))


def assert_inventory_closed(repo_root: Path) -> dict[str, object]:
    records = collect_records(repo_root)
    report = report_from_records(records)
    unknowns = unknown_records(records)
    if unknowns:
        joined = "; ".join(f"{item.path}: {', '.join(item.evidence)}" for item in unknowns)
        raise ScanPerformanceInventoryError(f"unclassified scanners: {joined}")
    return report


def measure_tiny_fixture(kind: str, n_files: int = 4) -> dict[str, object]:
    """Measure visit counts on a tiny bounded fixture. Never used for repo reports."""
    if n_files < 1 or n_files > 16:
        raise ScanPerformanceInventoryError("fixture n_files must be in 1..16")
    if kind not in HOTSPOT_CLASSES and kind != LINEAR_CLASS:
        raise ScanPerformanceInventoryError(f"unsupported fixture kind: {kind}")

    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        for index in range(n_files):
            (root / f"f{index}.txt").write_text(f"{index}\n", encoding="utf-8")

        visits = 0
        git_calls = 0
        if kind == LINEAR_CLASS:
            for path in root.iterdir():
                if path.is_file():
                    visits += 1
        elif kind == "repeated_full_tree_walk":
            for _repeat in range(2):
                for path in root.iterdir():
                    if path.is_file():
                        visits += 1
        elif kind == "quadratic_nested_walk":
            files = [path for path in root.iterdir() if path.is_file()]
            for _left in files:
                for _right in files:
                    visits += 1
        elif kind == "git_subprocess_per_file":
            for path in root.iterdir():
                if path.is_file():
                    visits += 1
                    git_calls += 1

    return {
        "kind": kind,
        "n_files": n_files,
        "visits": visits,
        "git_calls": git_calls,
        "timing": None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to inventory (defaults to this checkout)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = assert_inventory_closed(args.root)
    except ScanPerformanceInventoryError as exc:
        print(f"scan-performance-inventory: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2, separators=(",", ": ")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
