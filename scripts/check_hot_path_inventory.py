#!/usr/bin/env python3
"""Fail-closed inventory of known/measured hot paths and evidence gaps.

Issue #969 Seed 24 (``reserve-S152-hot-path-inventory``) classifies an
explicit catalog of hot-path candidates plus AST-discovered identifiers
whose names contain ``hot_path`` / ``hotpath`` / ``benchmark`` under
``scripts/``, ``skeleton/``, and ``backend/``.

Classes:

* measured — a named benchmark/test file exists, or a recorded metric
  field is paired with a real time-measurement API
* documented — source comments/docstrings call it a hot path, but there
  is no measurement evidence
* unknown_gap — catalogued or discovered, with neither measurement nor
  hot-path documentation
* unknown — unreadable or unparseable (always a gate failure)

This inventory does not rewrite hot paths, does not invent wall-clock
timings for the live repository, and does not own scan-performance (S029),
hidden-network (S026), or property-test (S081) inventories. Simulated or
random “benchmark” numbers are not measurement evidence.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import stat
import sys
import tempfile
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


TASK_KEY = "reserve-S152-hot-path-inventory"
CONFLICT_DOMAIN = "perf.readonly.hot_path_inventory"
INVENTORY_VERSION = 1
EVIDENCE_KIND = "structural"

CLASS_MEASURED = "measured"
CLASS_DOCUMENTED = "documented"
CLASS_UNKNOWN_GAP = "unknown_gap"
CLASS_UNKNOWN = "unknown"
CLASSIFICATIONS = (
    CLASS_MEASURED,
    CLASS_DOCUMENTED,
    CLASS_UNKNOWN_GAP,
    CLASS_UNKNOWN,
)

SCAN_ROOTS = ("scripts", "skeleton", "backend")
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "satellites",
        "branch-snapshots",
        "legacy_root",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)
SKIP_RELATIVE_PATHS = frozenset({"scripts/check_hot_path_inventory.py"})
TEST_DIR_NAMES = frozenset({"tests", "testing", "test"})

# Require a hot_path token, not a substring of snapshot_path.
HOT_NAME_RE = re.compile(r"(?:^|_)hot_path|hotpath|benchmark", re.IGNORECASE)
HOT_DOC_RE = re.compile(r"hot[\s_-]*path", re.IGNORECASE)
EVIDENCE_NAME_RE = re.compile(r"hot_path|hotpath|benchmark", re.IGNORECASE)

METRIC_FIELDS = frozenset(
    {
        "elapsed_seconds",
        "elapsed_ns",
        "duration_ms",
        "total_ms",
        "mean_ms",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "max_ms",
        "iterations_per_second",
        "timing",
    }
)
TIME_API_ATTRS = frozenset(
    {
        "perf_counter",
        "perf_counter_ns",
        "monotonic",
        "monotonic_ns",
        "time_ns",
        "process_time",
        "process_time_ns",
        "thread_time",
        "thread_time_ns",
    }
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class HotPathInventoryError(RuntimeError):
    """Raised when the inventory cannot classify a candidate fail-closed."""


@dataclass(frozen=True)
class CatalogEntry:
    """One explicit hot-path candidate. Not evidence by itself."""

    path_id: str
    path: str
    symbol: str
    evidence_files: tuple[str, ...]
    notes: str = ""


# Production surfaces named as hot paths in tests/comments, plus the
# observational frontier benchmark scripts. Catalog membership is not
# measurement evidence.
HOT_PATH_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        path_id="api.middleware.install_gate",
        path="skeleton/api/middleware.py",
        symbol="install_gate",
        evidence_files=("tests/test_backend_request_hot_path.py",),
        notes="API request middleware; named hot-path regression test.",
    ),
    CatalogEntry(
        path_id="retrieval.cache.ResultCache",
        path="skeleton/retrieval/cache.py",
        symbol="ResultCache",
        evidence_files=("skeleton/testing/test_retrieval_hot_path.py",),
        notes="Bounded retrieval result cache.",
    ),
    CatalogEntry(
        path_id="retrieval.quad.QuadRetriever",
        path="skeleton/retrieval/quad.py",
        symbol="QuadRetriever",
        evidence_files=("skeleton/testing/test_retrieval_hot_path.py",),
        notes="Quad retrieval fan-in with bounded cache.",
    ),
    CatalogEntry(
        path_id="retrieval.index.InvertedIndex",
        path="skeleton/retrieval/index.py",
        symbol="InvertedIndex",
        evidence_files=("skeleton/testing/test_retrieval_hot_path.py",),
        notes="In-process postings path used by retrieval tests.",
    ),
    CatalogEntry(
        path_id="api.gateway.APIGateway.handle",
        path="skeleton/api/gateway.py",
        symbol="handle",
        evidence_files=(),
        notes="Gateway request path, including the unlimited-route skip.",
    ),
    CatalogEntry(
        path_id="observability.profiler.hot_paths",
        path="skeleton/observability/profiler.py",
        symbol="hot_paths",
        evidence_files=(),
        notes="Profiler aggregation of recorded span totals.",
    ),
    CatalogEntry(
        path_id="backend.runtime_health.snapshot",
        path="backend/core/runtime_health.py",
        symbol="snapshot",
        evidence_files=(),
        notes="Documented no-disk-I/O snapshot hot path.",
    ),
    CatalogEntry(
        path_id="backend.perf.TTLCache",
        path="backend/core/perf.py",
        symbol="TTLCache",
        evidence_files=(),
        notes="Documented in-process cache for common hot paths.",
    ),
    CatalogEntry(
        path_id="omega.integration._grow",
        path="backend/gameforge/omega/integration.py",
        symbol="_grow",
        evidence_files=(),
        notes="Documented emission path that must not await a DB round-trip.",
    ),
    CatalogEntry(
        path_id="frontier.benchmark.achievements",
        path="scripts/benchmark_frontier_achievements.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_achievement_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.aquarium",
        path="scripts/benchmark_frontier_aquarium.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_aquarium_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.bait",
        path="scripts/benchmark_frontier_bait.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_bait_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.biotope",
        path="scripts/benchmark_frontier_biotope.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_biotope_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.breeding",
        path="scripts/benchmark_frontier_breeding.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_breeding_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.cooking",
        path="scripts/benchmark_frontier_cooking.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_cooking_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.crafting",
        path="scripts/benchmark_frontier_crafting.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_crafting_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.energy",
        path="scripts/benchmark_frontier_energy.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_energy_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.equipment",
        path="scripts/benchmark_frontier_equipment.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_equipment_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.events",
        path="scripts/benchmark_frontier_events.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_event_benchmark.py",),
    ),
    CatalogEntry(
        path_id="frontier.benchmark.memory",
        path="scripts/benchmark_frontier_memory.py",
        symbol="run_benchmark",
        evidence_files=("skeleton/testing/test_frontier_memory_benchmark.py",),
    ),
)


@dataclass(frozen=True)
class HotPathRecord:
    """One classified hot-path candidate."""

    path: str
    symbol: str
    classification: str
    origin: str
    evidence: tuple[str, ...]
    evidence_files: tuple[str, ...]
    metric_fields: tuple[str, ...]
    path_id: str = ""
    timing: None = None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        payload["evidence_files"] = list(self.evidence_files)
        payload["metric_fields"] = list(self.metric_fields)
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


def _enclosing_function_or_class(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None:
    for ancestor in _ancestors(node, parents):
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return ancestor
    return None


def name_matches_hot_path(name: str) -> bool:
    """True when ``name`` contains hot_path/hotpath/benchmark as a token."""
    return HOT_NAME_RE.search(name) is not None


def _is_test_relative(relative: str) -> bool:
    parts = Path(relative).parts
    if any(part in TEST_DIR_NAMES for part in parts):
        return True
    filename = Path(relative).name
    return filename.startswith("test_") or filename.endswith("_test.py")


def _is_named_evidence_file(relative: str) -> bool:
    return EVIDENCE_NAME_RE.search(Path(relative).name) is not None


def _walk_error(exc: OSError) -> None:
    raise HotPathInventoryError(f"hot-path traversal failure: {type(exc).__name__}") from None


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield Python files without following symlinks or hiding traversal errors."""
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise HotPathInventoryError(f"scan root metadata failure: {type(exc).__name__}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise HotPathInventoryError("scan root must not be a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise HotPathInventoryError("scan root is not a directory")

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
                raise HotPathInventoryError(
                    f"{path}: hot-path metadata failure: {type(exc).__name__}"
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
        raise HotPathInventoryError("required scan root missing: " + ", ".join(missing))
    return roots


def _read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, type(exc).__name__


def _parse(source: str, filename: str) -> tuple[ast.AST | None, str | None]:
    try:
        return ast.parse(source, filename=filename), None
    except SyntaxError:
        return None, "syntax error"
    except ValueError:
        return None, "parse error"


def _docstrings(tree: ast.AST) -> tuple[str, ...]:
    docs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if doc:
                docs.append(doc)
    return tuple(docs)


def _comments(source: str) -> tuple[str, ...] | str:
    comments: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comments.append(token.string)
    except (tokenize.TokenError, SyntaxError, TimeoutError):
        return "tokenize error"
    return tuple(comments)


def documentation_hits(source: str, tree: ast.AST) -> tuple[str, ...] | str:
    """Return hot-path documentation snippets, or a fail-closed tokenize error."""
    comments = _comments(source)
    if isinstance(comments, str):
        return comments
    hits: list[str] = []
    seen: set[str] = set()
    for text in (*_docstrings(tree), *comments):
        if HOT_DOC_RE.search(text) is None:
            continue
        snippet = " ".join(text.split())
        if snippet and snippet not in seen:
            seen.add(snippet)
            hits.append(snippet)
    return tuple(hits)


def _has_time_api(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in TIME_API_ATTRS:
            return True
        if isinstance(child, ast.Name) and child.id in TIME_API_ATTRS:
            return True
    return False


def _metric_fields(node: ast.AST) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for child in ast.walk(node):
        key: str | None = None
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            key = child.value
        elif isinstance(child, ast.keyword) and child.arg:
            key = child.arg
        elif isinstance(child, ast.Attribute):
            key = child.attr
        if key in METRIC_FIELDS and key not in seen:
            seen.add(key)
            found.append(key)
    return tuple(found)


def _find_symbol_node(tree: ast.AST, symbol: str) -> ast.AST | None:
    if symbol in {"<module>", ""}:
        return tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return node
    return None


def _class_for_function(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.ClassDef | None:
    for ancestor in _ancestors(node, parents):
        if isinstance(ancestor, ast.ClassDef):
            return ancestor
        if isinstance(ancestor, ast.Module):
            return None
    return None


def recorded_metric_fields(tree: ast.AST, symbol: str) -> tuple[str, ...]:
    """Metric fields that share a function/class with a real time API."""
    parents = _parents(tree)
    target = _find_symbol_node(tree, symbol)
    if target is None:
        return ()
    scopes: list[ast.AST] = [target]
    if isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)):
        owner = _class_for_function(target, parents)
        if owner is not None:
            scopes.append(owner)
    if not any(_has_time_api(scope) for scope in scopes):
        return ()
    fields: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        for field in _metric_fields(scope):
            if field not in seen:
                seen.add(field)
                fields.append(field)
    return tuple(fields)


def discover_symbols(tree: ast.AST) -> tuple[str, ...]:
    """Return matching function/class/module-level names."""
    parents = _parents(tree)
    names: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        found: str | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found = node.name
        elif isinstance(node, ast.Assign):
            if _enclosing_function_or_class(node, parents) is not None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and name_matches_hot_path(target.id):
                    found = target.id
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _enclosing_function_or_class(node, parents) is not None:
                continue
            found = node.target.id
        if found and name_matches_hot_path(found) and found not in seen:
            seen.add(found)
            names.append(found)
    return tuple(names)


def conventional_evidence_files(relative: str) -> tuple[str, ...]:
    stem = Path(relative).stem
    if not stem.startswith("benchmark_"):
        return ()
    topic = stem[len("benchmark_") :]
    options = [
        f"skeleton/testing/test_{topic}_benchmark.py",
        f"tests/test_{topic}_benchmark.py",
        f"backend/tests/test_{topic}_benchmark.py",
    ]
    if topic.endswith("s"):
        options.append(f"skeleton/testing/test_{topic[:-1]}_benchmark.py")
    return tuple(options)


def prove_evidence_files(
    repo_root: Path, relative: str, claimed: tuple[str, ...]
) -> tuple[str, ...]:
    proven: list[str] = []
    seen: set[str] = set()
    for candidate in (*claimed, *conventional_evidence_files(relative)):
        if candidate in seen:
            continue
        seen.add(candidate)
        if not _is_named_evidence_file(candidate):
            continue
        path = repo_root / candidate
        try:
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        proven.append(candidate)
    return tuple(proven)


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


def classify_source(
    source: str,
    *,
    filename: str,
    symbol: str,
    origin: str,
    path_id: str = "",
    claimed_evidence: tuple[str, ...] = (),
    proven_evidence: tuple[str, ...] = (),
) -> HotPathRecord:
    tree, parse_error = _parse(source, filename)
    if tree is None:
        return HotPathRecord(
            path=filename,
            symbol=symbol,
            classification=CLASS_UNKNOWN,
            origin=origin,
            evidence=(parse_error or "parse error",),
            evidence_files=(),
            metric_fields=(),
            path_id=path_id,
        )

    docs = documentation_hits(source, tree)
    if isinstance(docs, str):
        return HotPathRecord(
            path=filename,
            symbol=symbol,
            classification=CLASS_UNKNOWN,
            origin=origin,
            evidence=(docs,),
            evidence_files=(),
            metric_fields=(),
            path_id=path_id,
        )

    metrics = recorded_metric_fields(tree, symbol)
    catalog_symbol_missing = bool(path_id) and symbol not in {"<module>", ""} and _find_symbol_node(
        tree, symbol
    ) is None

    evidence: list[str] = []
    if proven_evidence:
        evidence.append("named evidence file: " + ", ".join(proven_evidence))
    if metrics:
        evidence.append("recorded metric field: " + ", ".join(metrics))
    if docs:
        evidence.append("documented hot path in comments/docstrings")
    if catalog_symbol_missing:
        evidence.append(f"catalog symbol not found in AST: {symbol}")
    claimed_missing = [item for item in claimed_evidence if item not in proven_evidence]
    if claimed_missing:
        evidence.append("claimed evidence missing or not a named benchmark/test: " + ", ".join(claimed_missing))
    if not evidence:
        evidence.append("no measurement evidence and no hot-path documentation")

    if proven_evidence or metrics:
        classification = CLASS_MEASURED
    elif docs and not catalog_symbol_missing:
        classification = CLASS_DOCUMENTED
    else:
        classification = CLASS_UNKNOWN_GAP

    return HotPathRecord(
        path=filename,
        symbol=symbol,
        classification=classification,
        origin=origin,
        evidence=_dedupe(evidence),
        evidence_files=proven_evidence,
        metric_fields=metrics,
        path_id=path_id,
    )


def classify_path(
    path: Path,
    *,
    display: str,
    symbol: str,
    origin: str,
    path_id: str = "",
    claimed_evidence: tuple[str, ...] = (),
    proven_evidence: tuple[str, ...] = (),
) -> HotPathRecord:
    source, error = _read_text(path)
    if source is None:
        return HotPathRecord(
            path=display,
            symbol=symbol,
            classification=CLASS_UNKNOWN,
            origin=origin,
            evidence=(f"unreadable: {error}",),
            evidence_files=(),
            metric_fields=(),
            path_id=path_id,
        )
    return classify_source(
        source,
        filename=display,
        symbol=symbol,
        origin=origin,
        path_id=path_id,
        claimed_evidence=claimed_evidence,
        proven_evidence=proven_evidence,
    )


def unknown_file_record(display: str, reason: str, *, origin: str = "ast") -> HotPathRecord:
    return HotPathRecord(
        path=display,
        symbol="<unknown>",
        classification=CLASS_UNKNOWN,
        origin=origin,
        evidence=(reason,),
        evidence_files=(),
        metric_fields=(),
    )


def collect_records(
    repo_root: Path, *, catalog: tuple[CatalogEntry, ...] | None = None
) -> list[HotPathRecord]:
    if catalog is None:
        catalog = HOT_PATH_CATALOG
    merged: dict[tuple[str, str], HotPathRecord] = {}
    catalog_by_path: dict[str, list[CatalogEntry]] = {}
    for entry in catalog:
        catalog_by_path.setdefault(entry.path, []).append(entry)

    for entry in catalog:
        path = repo_root / entry.path
        proven = prove_evidence_files(repo_root, entry.path, entry.evidence_files)
        if not path.exists():
            record = HotPathRecord(
                path=entry.path,
                symbol=entry.symbol,
                classification=CLASS_UNKNOWN,
                origin="catalog",
                evidence=("catalog path missing",),
                evidence_files=(),
                metric_fields=(),
                path_id=entry.path_id,
            )
        else:
            record = classify_path(
                path,
                display=entry.path,
                symbol=entry.symbol,
                origin="catalog",
                path_id=entry.path_id,
                claimed_evidence=entry.evidence_files,
                proven_evidence=proven,
            )
        merged[(entry.path, entry.symbol)] = record

    for root in scan_roots_for(repo_root):
        for path in iter_python_files(root):
            display = _display(path, repo_root)
            if display in SKIP_RELATIVE_PATHS:
                continue
            source, error = _read_text(path)
            if source is None:
                merged.setdefault(
                    (display, "<unknown>"),
                    unknown_file_record(display, f"unreadable: {error}"),
                )
                continue
            tree, parse_error = _parse(source, display)
            if tree is None:
                merged.setdefault(
                    (display, "<unknown>"),
                    unknown_file_record(display, parse_error or "parse error"),
                )
                continue
            if _is_test_relative(display):
                continue
            for symbol in discover_symbols(tree):
                key = (display, symbol)
                if key in merged:
                    existing = merged[key]
                    if existing.origin == "catalog":
                        merged[key] = HotPathRecord(
                            path=existing.path,
                            symbol=existing.symbol,
                            classification=existing.classification,
                            origin="catalog+ast",
                            evidence=existing.evidence,
                            evidence_files=existing.evidence_files,
                            metric_fields=existing.metric_fields,
                            path_id=existing.path_id,
                        )
                    continue
                claimed = tuple(
                    file
                    for entry in catalog_by_path.get(display, ())
                    if entry.symbol == symbol
                    for file in entry.evidence_files
                )
                proven = prove_evidence_files(repo_root, display, claimed)
                merged[key] = classify_source(
                    source,
                    filename=display,
                    symbol=symbol,
                    origin="ast",
                    proven_evidence=proven,
                    claimed_evidence=claimed,
                )

    records = list(merged.values())
    records.sort(key=lambda record: (record.path, record.symbol, record.path_id))
    return records


def unknown_records(records: Iterable[HotPathRecord]) -> list[HotPathRecord]:
    return [record for record in records if record.classification == CLASS_UNKNOWN]


def gap_records(records: Iterable[HotPathRecord]) -> list[HotPathRecord]:
    return [record for record in records if record.classification == CLASS_UNKNOWN_GAP]


def count_class(records: Iterable[HotPathRecord], classification: str) -> int:
    return sum(1 for record in records if record.classification == classification)


def report_from_records(records: list[HotPathRecord]) -> dict[str, object]:
    if not records:
        raise HotPathInventoryError("hot-path coverage failure: zero candidates classified")
    return {
        "task_key": TASK_KEY,
        "conflict_domain": CONFLICT_DOMAIN,
        "inventory_version": INVENTORY_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "scanned_roots": list(SCAN_ROOTS),
        "candidate_count": len(records),
        "measured_count": count_class(records, CLASS_MEASURED),
        "documented_count": count_class(records, CLASS_DOCUMENTED),
        "unknown_gap_count": count_class(records, CLASS_UNKNOWN_GAP),
        "unknown_count": count_class(records, CLASS_UNKNOWN),
        "classifications": list(CLASSIFICATIONS),
        "records": [record.as_dict() for record in records],
        "gaps": [record.as_dict() for record in gap_records(records)],
    }


def inventory_report(
    repo_root: Path, *, catalog: tuple[CatalogEntry, ...] | None = None
) -> dict[str, object]:
    return report_from_records(collect_records(repo_root, catalog=catalog))


def assert_inventory_closed(
    repo_root: Path, *, catalog: tuple[CatalogEntry, ...] | None = None
) -> dict[str, object]:
    records = collect_records(repo_root, catalog=catalog)
    report = report_from_records(records)
    unknowns = unknown_records(records)
    if unknowns:
        joined = "; ".join(f"{item.path}:{item.symbol}: {', '.join(item.evidence)}" for item in unknowns)
        raise HotPathInventoryError(f"unclassified hot paths: {joined}")
    return report


def measure_tiny_fixture(n_files: int = 4) -> dict[str, object]:
    """Count bounded visits on a tiny fixture. Never attached to live reports."""
    if n_files < 1 or n_files > 16:
        raise HotPathInventoryError("fixture n_files must be in 1..16")
    with tempfile.TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        for index in range(n_files):
            (root / f"f{index}.txt").write_text(f"{index}\n", encoding="utf-8")
        visits = 0
        for path in root.iterdir():
            if path.is_file():
                visits += 1
    return {
        "n_files": n_files,
        "visits": visits,
        "timing": {"bounded_visits": visits},
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
    except HotPathInventoryError as exc:
        print(f"hot-path-inventory: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2, separators=(",", ": ")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
