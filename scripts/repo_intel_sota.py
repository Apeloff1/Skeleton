#!/usr/bin/env python3
"""SOTA repository knowledge graph layered on the fast Git-backed repo index.

This module deliberately remains stdlib-only. It reuses scripts/repo_intel.py for
Git/index/config contracts, then adds blob-cached semantic indexing, a typed forward
and reverse graph, ownership/risk zones, dependency-cycle detection, impact queries,
telemetry, and machine query commands.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
import json
from pathlib import Path
import posixpath
import re
import sys
import time
from typing import Any, Iterable

import repo_intel as base

ROOT = base.ROOT
DEFAULT_OUT = base.DEFAULT_OUT
SOURCE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx"}
JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
TEXT_LIMIT = 2 * 1024 * 1024


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_text(path: str) -> str | None:
    target = ROOT / path
    try:
        if target.stat().st_size > TEXT_LIMIT:
            return None
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def language_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python", ".pyi": "python",
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".json": "json", ".yml": "yaml", ".yaml": "yaml",
        ".toml": "toml", ".md": "markdown", ".sh": "shell",
    }.get(suffix, "binary-or-other" if suffix == "" else suffix.lstrip("."))


def _owner_for(path: str, ownership: dict[str, Any]) -> dict[str, str] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for zone in ownership.get("zones", []):
        for prefix in zone.get("prefixes", []):
            normalized = prefix.rstrip("/")
            if path == normalized or path.startswith(prefix):
                candidates.append((len(prefix), zone))
    if not candidates:
        return None
    zone = max(candidates, key=lambda item: item[0])[1]
    return {"id": str(zone["id"]), "risk": str(zone.get("risk", "unknown"))}


def _flags(path: str, role: str, cfg: dict[str, Any]) -> dict[str, bool]:
    name = Path(path).name.lower()
    lower = path.lower()
    is_test = (
        name.startswith("test_") or name.endswith("_test.py") or
        "/tests/" in f"/{lower}" or lower.startswith("tests/") or
        lower.startswith("skeleton/testing/")
    )
    build_affecting = any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in cfg.get("build_affecting_prefixes", [])
    )
    sensitive = (
        path.startswith(".github/") or path.startswith("scripts/security/") or
        "security" in lower or "secret" in lower or "auth" in lower or
        name in {"dockerfile", "pyproject.toml", "package.json", "requirements.txt"}
    )
    generated = lower.startswith(("dist/", "build/", ".cache/"))
    return {
        "test": is_test,
        "build_affecting": build_affecting,
        "security_sensitive": sensitive,
        "generated": generated,
        "semantic_supported": Path(path).suffix.lower() in SOURCE_SUFFIXES,
        "manifest": role == "dependency-manifest",
        "workflow": role == "ci-workflow",
    }


class PythonExtractor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.tests: list[str] = []

    def _symbol(self, node: ast.AST, name: str, kind: str) -> None:
        qualified = ".".join([*self.scope, name])
        self.symbols.append({
            "name": name,
            "qualified_name": qualified,
            "kind": kind,
            "line": int(getattr(node, "lineno", 0)),
            "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 0))),
            "precision": "ast",
        })
        if name.startswith("test_"):
            self.tests.append(qualified)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbol(node, node.name, "class")
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._symbol(node, node.name, "function")
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._symbol(node, node.name, "async-function")
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({"module": alias.name, "level": 0, "precision": "ast"})

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.imports.append({
            "module": module,
            "level": int(node.level),
            "names": [alias.name for alias in node.names],
            "precision": "ast",
        })


def _extract_python(path: str, text: str) -> dict[str, Any]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return {
            "language": "python", "symbols": [], "imports": [], "tests": [],
            "parse_error": f"{exc.msg}:{exc.lineno}", "precision": "ast",
        }
    visitor = PythonExtractor(path)
    visitor.visit(tree)
    return {
        "language": "python",
        "symbols": visitor.symbols,
        "imports": visitor.imports,
        "tests": visitor.tests,
        "parse_error": None,
        "precision": "ast",
    }


_JS_IMPORT_RE = re.compile(
    r"(?:import\s+(?:[^'\"]+?\s+from\s+)?|export\s+[^'\"]+?\s+from\s+|require\(\s*)"
    r"['\"]([^'\"]+)['\"]"
)
_JS_SYMBOL_RE = re.compile(
    r"(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:class|function)\s+([A-Za-z_$][\w$]*)"
)
_JS_CONST_EXPORT_RE = re.compile(r"export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)")


def _extract_js(path: str, text: str) -> dict[str, Any]:
    symbols = [
        {"name": m.group(1), "qualified_name": m.group(1), "kind": "export-or-declaration", "line": text.count("\n", 0, m.start()) + 1, "precision": "lexical"}
        for m in _JS_SYMBOL_RE.finditer(text)
    ]
    symbols.extend(
        {"name": m.group(1), "qualified_name": m.group(1), "kind": "export", "line": text.count("\n", 0, m.start()) + 1, "precision": "lexical"}
        for m in _JS_CONST_EXPORT_RE.finditer(text)
    )
    imports = [{"module": m.group(1), "level": 0, "precision": "lexical"} for m in _JS_IMPORT_RE.finditer(text)]
    tests = [s["qualified_name"] for s in symbols if str(s["name"]).startswith(("test", "should"))]
    return {
        "language": language_for(path), "symbols": symbols, "imports": imports,
        "tests": tests, "parse_error": None, "precision": "lexical",
    }


def semantic_record(path: str, blob: str) -> dict[str, Any]:
    text = _read_text(path)
    if text is None:
        return {
            "blob": blob, "path": path, "language": language_for(path), "symbols": [],
            "imports": [], "tests": [], "parse_error": "unreadable-or-too-large", "precision": "metadata",
        }
    suffix = Path(path).suffix.lower()
    if suffix in {".py", ".pyi"}:
        record = _extract_python(path, text)
    elif suffix in JS_SUFFIXES:
        record = _extract_js(path, text)
    else:
        record = {"language": language_for(path), "symbols": [], "imports": [], "tests": [], "parse_error": None, "precision": "metadata"}
    record.update({"blob": blob, "path": path})
    return record


def _python_modules(files: Iterable[dict[str, Any]]) -> dict[str, str]:
    modules: dict[str, str] = {}
    for row in files:
        path = row["path"]
        if Path(path).suffix.lower() not in {".py", ".pyi"}:
            continue
        p = Path(path)
        parts = list(p.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        if parts:
            modules[".".join(parts)] = path
    return modules


def _resolve_python_import(source: str, imp: dict[str, Any], modules: dict[str, str]) -> str | None:
    module = str(imp.get("module", ""))
    level = int(imp.get("level", 0))
    if level:
        src_parts = list(Path(source).with_suffix("").parts[:-1])
        keep = max(0, len(src_parts) - level + 1)
        module = ".".join([*src_parts[:keep], *([module] if module else [])])
    candidates = [module]
    names = imp.get("names") or []
    candidates.extend(f"{module}.{name}".strip(".") for name in names if name != "*")
    for candidate in candidates:
        if candidate in modules:
            return modules[candidate]
        parts = candidate.split(".") if candidate else []
        while len(parts) > 1:
            parts.pop()
            prefix = ".".join(parts)
            if prefix in modules:
                return modules[prefix]
    return None


def _resolve_js_import(source: str, specifier: str, paths: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    raw = posixpath.normpath(posixpath.join(posixpath.dirname(source), specifier))
    if raw == ".." or raw.startswith("../") or raw.startswith("/"):
        return None
    candidates = [raw]
    candidates.extend(raw + suffix for suffix in JS_SUFFIXES)
    candidates.extend(posixpath.join(raw, f"index{suffix}") for suffix in JS_SUFFIXES)
    for candidate in candidates:
        if candidate in paths:
            return candidate
    return None


def _test_candidates(path: str, all_paths: set[str]) -> list[str]:
    name = Path(path).name
    stem = Path(path).stem
    if not (name.startswith("test_") or stem.endswith("_test")):
        return []
    core = stem.removeprefix("test_").removesuffix("_test")
    if not core:
        return []
    matches = [
        p for p in all_paths
        if Path(p).stem == core and p != path and Path(p).suffix.lower() in SOURCE_SUFFIXES
    ]
    return sorted(matches)[:20]


def _build_edges(
    files: list[dict[str, Any]], semantic: dict[str, dict[str, Any]], ownership: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    paths = {row["path"] for row in files}
    py_modules = _python_modules(files)

    for row in files:
        path = row["path"]
        file_id = f"file:{path}"
        edges.append({"from": f"subsystem:{row['subsystem']}", "to": file_id, "type": "contains", "precision": "structural"})
        owner = row.get("owner") or _owner_for(path, ownership)
        if owner:
            edges.append({"from": file_id, "to": f"owner:{owner['id']}", "type": "owned-by", "precision": "structural"})
        rec = semantic.get(path)
        if rec:
            for item in rec.get("symbols", []):
                symbol = {
                    **item,
                    "id": f"symbol:{path}:{item['qualified_name']}",
                    "path": path,
                    "language": rec.get("language"),
                }
                symbols.append(symbol)
                edges.append({"from": file_id, "to": symbol["id"], "type": "contains", "precision": item.get("precision", rec.get("precision", "lexical"))})
            for imp in rec.get("imports", []):
                target: str | None = None
                if rec.get("language") == "python":
                    target = _resolve_python_import(path, imp, py_modules)
                elif rec.get("language") in {"javascript", "typescript"}:
                    target = _resolve_js_import(path, str(imp.get("module", "")), paths)
                if target and target != path:
                    edges.append({"from": file_id, "to": f"file:{target}", "type": "imports", "precision": imp.get("precision", rec.get("precision", "lexical"))})
            for target in _test_candidates(path, paths):
                edges.append({"from": file_id, "to": f"file:{target}", "type": "tests", "precision": "structural"})
    # Stable de-duplication.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for edge in edges:
        key = (edge["from"], edge["to"], edge["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(edge)
    deduped.sort(key=lambda e: (e["from"], e["to"], e["type"]))
    symbols.sort(key=lambda s: (s["path"], int(s.get("line", 0)), s["qualified_name"]))
    return deduped, symbols


def _reverse_edges(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in edges:
        reverse[edge["to"]].append({"from": edge["from"], "type": edge["type"], "precision": edge.get("precision", "unknown")})
    return {key: sorted(value, key=lambda x: (x["from"], x["type"])) for key, value in sorted(reverse.items())}


def _dependency_cycles(edges: list[dict[str, Any]]) -> list[list[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["type"] == "imports" and edge["from"].startswith("file:") and edge["to"].startswith("file:"):
            graph[edge["from"]].append(edge["to"])

    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in graph.get(node, []):
            if nxt not in indices:
                strongconnect(nxt)
                lowlink[node] = min(lowlink[node], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node] = min(lowlink[node], indices[nxt])
        if lowlink[node] == indices[node]:
            component: list[str] = []
            while stack:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item.removeprefix("file:"))
                if item == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            strongconnect(node)
    return sorted(components, key=lambda c: (-len(c), c))


def enrich_snapshot(snapshot: dict[str, Any], out: Path) -> dict[str, Any]:
    start = time.perf_counter()
    cfg = base.load_json("config.json")
    ownership = base.load_json("ownership.json")
    cache_path = out / "semantic-cache.json"
    cache = _read_json(cache_path, {"schema": 1, "objects": {}})
    objects = cache.setdefault("objects", {})
    semantic: dict[str, dict[str, Any]] = {}
    hits = misses = failures = supported = 0

    for row in snapshot["files"]:
        row["language"] = language_for(row["path"])
        row["owner"] = _owner_for(row["path"], ownership)
        row["flags"] = _flags(row["path"], row["role"], cfg)
        if not row["flags"]["semantic_supported"]:
            continue
        supported += 1
        key = str(row["blob"])
        cached = objects.get(key)
        if isinstance(cached, dict) and cached.get("path-independent-schema") == 1:
            rec = dict(cached["record"])
            rec["path"] = row["path"]
            rec["blob"] = key
            hits += 1
        else:
            rec = semantic_record(row["path"], key)
            portable = dict(rec)
            portable.pop("path", None)
            portable.pop("blob", None)
            objects[key] = {"path-independent-schema": 1, "record": portable}
            misses += 1
        if rec.get("parse_error"):
            failures += 1
        semantic[row["path"]] = rec

    semantic_done = time.perf_counter()
    edges, symbols = _build_edges(snapshot["files"], semantic, ownership)
    reverse = _reverse_edges(edges)
    cycles = _dependency_cycles(edges)
    nodes = (
        [{"id": f"file:{r['path']}", "type": "file", "path": r["path"], "subsystem": r["subsystem"]} for r in snapshot["files"]]
        + [{"id": s["id"], "type": "symbol", "path": s["path"], "name": s["qualified_name"]} for s in symbols]
        + [{"id": f"subsystem:{s['id']}", "type": "subsystem", "name": s.get("name", s["id"])} for s in snapshot["subsystems"]]
        + [{"id": f"owner:{z['id']}", "type": "owner", "risk": z.get("risk", "unknown")} for z in ownership.get("zones", [])]
    )
    graph_done = time.perf_counter()
    total = max(graph_done - start, 0.000001)
    owned = sum(1 for row in snapshot["files"] if row.get("owner"))
    metrics = {
        "semantic_supported_files": supported,
        "semantic_cache_hits": hits,
        "semantic_cache_misses": misses,
        "semantic_parse_failures": failures,
        "semantic_cache_hit_ratio": hits / max(1, hits + misses),
        "python_parse_success_ratio": 1.0 - failures / max(1, supported),
        "owned_files": owned,
        "unowned_files": len(snapshot["files"]) - owned,
        "owned_file_ratio": owned / max(1, len(snapshot["files"])),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "dependency_cycles": len(cycles),
        "snapshot_wall_ms": round(total * 1000, 3),
        "semantic_wall_ms": round((semantic_done - start) * 1000, 3),
        "graph_wall_ms": round((graph_done - semantic_done) * 1000, 3),
    }
    snapshot.update({
        "schema": 3,
        "symbols": symbols,
        "semantic": semantic,
        "graph": {"nodes": nodes, "edges": edges, "reverse_edges": reverse, "dependency_cycles": cycles},
        "metrics": metrics,
    })
    # Prune cache to currently reachable blob objects so it cannot grow forever.
    live_blobs = {str(r["blob"]) for r in snapshot["files"] if r.get("flags", {}).get("semantic_supported")}
    cache["objects"] = {key: value for key, value in objects.items() if key in live_blobs}
    _write_json(cache_path, cache)
    return snapshot


def _build_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    mapping = base.build_map(snapshot)
    manifests = [r["path"] for r in snapshot["files"] if r["flags"]["manifest"]]
    workflows = [r["path"] for r in snapshot["files"] if r["flags"]["workflow"]]
    tests = [r["path"] for r in snapshot["files"] if r["flags"]["test"]]
    mapping.update({
        "schema": 3,
        "manifests": sorted(manifests),
        "workflows": sorted(workflows),
        "tests": sorted(tests),
        "graph_metrics": snapshot["metrics"],
        "dependency_cycles": snapshot["graph"]["dependency_cycles"],
    })
    return mapping


def _impact_from_paths(snapshot: dict[str, Any], changed: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    reverse = snapshot["graph"]["reverse_edges"]
    queue = deque(f"file:{p}" for p in changed)
    seen = set(queue)
    while queue:
        target = queue.popleft()
        for incoming in reverse.get(target, []):
            source = incoming["from"]
            if source.startswith("file:") and source not in seen:
                seen.add(source)
                queue.append(source)
    affected = sorted(node.removeprefix("file:") for node in seen if node.startswith("file:"))
    by_path = {row["path"]: row for row in snapshot["files"]}
    impacted_rows = [by_path[p] for p in affected if p in by_path]
    tests = sorted(r["path"] for r in impacted_rows if r["flags"]["test"])
    workflows = sorted(r["path"] for r in impacted_rows if r["flags"]["workflow"])
    subsystems = sorted({r["subsystem"] for r in impacted_rows})
    security_zones = sorted({r["owner"]["id"] for r in impacted_rows if r.get("owner") and r["owner"].get("risk") in {"critical", "high"}})
    gaps = base.feature_gaps(snapshot)
    impacted_set = set(affected)
    capabilities = sorted(
        cap["id"] for cap in gaps["capabilities"]
        if impacted_set.intersection(cap.get("evidence", []))
    )
    return {
        "schema": 1,
        "changed": sorted(changed),
        "affected_files": affected,
        "affected_file_count": len(affected),
        "subsystems": subsystems,
        "candidate_tests": tests,
        "workflows": workflows,
        "security_zones": security_zones,
        "capabilities": capabilities,
        "impact_wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "note": "Impact is conservative and preserves lower-precision dependency edges; candidate tests are not proof of sufficient coverage.",
    }


def snapshot_command(out: Path, base_ref: str = "origin/main") -> dict[str, Any]:
    base.validate_configs()
    out.mkdir(parents=True, exist_ok=True)
    snapshot = enrich_snapshot(base.build_snapshot(), out)
    gaps = base.feature_gaps(snapshot)
    sq = base.security_quality(snapshot)
    mapping = _build_map(snapshot)
    changed = base.changed_paths(base_ref)
    impact = _impact_from_paths(snapshot, changed)
    _write_json(out / "index.json", snapshot)
    _write_json(out / "graph.json", snapshot["graph"])
    _write_json(out / "symbols.json", {"schema": 1, "symbols": snapshot["symbols"]})
    _write_json(out / "build-map.json", mapping)
    _write_json(out / "impact.json", impact)
    _write_json(out / "gaps.json", gaps)
    _write_json(out / "security-quality.json", sq)
    _write_json(out / "metrics.json", snapshot["metrics"])
    notes = base.render_notes(snapshot, gaps, sq)
    notes += "\n## Graph / index health\n\n"
    notes += f"- Graph: **{snapshot['metrics']['graph_nodes']} nodes / {snapshot['metrics']['graph_edges']} edges**.\n"
    notes += f"- Semantic cache: **{snapshot['metrics']['semantic_cache_hit_ratio']:.1%} hit ratio** for this run.\n"
    notes += f"- Dependency cycles detected: **{snapshot['metrics']['dependency_cycles']}**.\n"
    notes += f"- Ownership coverage: **{snapshot['metrics']['owned_file_ratio']:.1%}**.\n"
    notes += f"- Current change impact: **{impact['affected_file_count']} files / {len(impact['subsystems'])} subsystems / {len(impact['candidate_tests'])} candidate tests**.\n"
    (out / "notes.md").write_text(notes, encoding="utf-8")
    print(
        "repo-intel-sota: "
        f"{snapshot['tracked_files']} files, {snapshot['metrics']['graph_nodes']} nodes, "
        f"{snapshot['metrics']['graph_edges']} edges, {snapshot['metrics']['dependency_cycles']} cycles, "
        f"{snapshot['metrics']['semantic_cache_hit_ratio']:.1%} semantic cache hits"
    )
    return snapshot


def load_or_build(out: Path) -> dict[str, Any]:
    path = out / "index.json"
    snapshot = _read_json(path, None)
    if not isinstance(snapshot, dict) or int(snapshot.get("schema", 0)) < 3:
        snapshot = snapshot_command(out)
    return snapshot


def query_command(out: Path, kind: str, value: str, transitive: bool) -> None:
    snapshot = load_or_build(out)
    if kind == "file":
        row = next((r for r in snapshot["files"] if r["path"] == value), None)
        payload = {"file": row, "semantic": snapshot.get("semantic", {}).get(value)}
    elif kind == "symbol":
        needle = value.lower()
        payload = {"symbols": [s for s in snapshot["symbols"] if needle in str(s.get("qualified_name", "")).lower()][:200]}
    elif kind in {"deps", "rdeps"}:
        start = f"file:{value}"
        adjacency: dict[str, list[str]] = defaultdict(list)
        if kind == "deps":
            for edge in snapshot["graph"]["edges"]:
                if edge["type"] == "imports":
                    adjacency[edge["from"]].append(edge["to"])
        else:
            for target, incoming in snapshot["graph"]["reverse_edges"].items():
                for edge in incoming:
                    if edge["type"] == "imports":
                        adjacency[target].append(edge["from"])
        found: set[str] = set()
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in adjacency.get(node, []):
                if nxt not in found:
                    found.add(nxt)
                    if transitive:
                        queue.append(nxt)
        payload = {kind: sorted(x.removeprefix("file:") for x in found if x.startswith("file:"))}
    elif kind == "subsystem":
        payload = {"files": [r for r in snapshot["files"] if r["subsystem"] == value]}
    else:
        raise RuntimeError(f"unsupported query kind: {kind}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def impact_command(out: Path, base_ref: str, paths: list[str]) -> None:
    snapshot = load_or_build(out)
    changed = sorted(set(paths or base.changed_paths(base_ref)))
    payload = _impact_from_paths(snapshot, changed)
    _write_json(out / "impact.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))


def doctor_command(out: Path) -> int:
    snapshot = load_or_build(out)
    metrics = snapshot["metrics"]
    issues: list[str] = []
    if metrics["semantic_parse_failures"]:
        issues.append(f"semantic parse failures={metrics['semantic_parse_failures']}")
    if metrics["unowned_files"]:
        issues.append(f"unowned files={metrics['unowned_files']}")
    if metrics["dependency_cycles"]:
        issues.append(f"dependency cycles={metrics['dependency_cycles']}")
    if not snapshot["graph"]["edges"]:
        issues.append("dependency graph has no edges")
    report = {
        "source_digest": snapshot["source_digest"],
        "healthy": not issues,
        "issues": issues,
        "metrics": metrics,
        "largest_cycles": snapshot["graph"]["dependency_cycles"][:10],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not issues else 1


def check_contracts() -> None:
    base.validate_configs()
    required = [
        "ownership.json", "query-contract.json", "quality-budgets.json", "index-schema.json",
        "export-contract.json", "telemetry-contract.json", "precision-policy.json", "evidence-levels.json",
    ]
    missing = [name for name in required if not (base.CONFIG_DIR / name).is_file()]
    if missing:
        raise RuntimeError(f"missing SOTA repo-intel contracts: {', '.join(missing)}")
    ownership = base.load_json("ownership.json")
    zone_ids = [z["id"] for z in ownership.get("zones", [])]
    if len(zone_ids) != len(set(zone_ids)):
        raise RuntimeError("ownership zone IDs must be unique")
    budgets = base.load_json("quality-budgets.json")
    if float(budgets["index_performance_targets"]["cache_hit_ratio_target"]) <= 0:
        raise RuntimeError("invalid semantic cache target")
    print(f"repo-intel-sota: contracts valid ({len(zone_ids)} ownership zones, {len(required)} extended contracts)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    snap.add_argument("--base", default="origin/main")
    check = sub.add_parser("check")
    check.add_argument("--gate", action="store_true")
    check.add_argument("--base", default="origin/main")
    gate = sub.add_parser("gate")
    gate.add_argument("--base", default="origin/main")
    impact = sub.add_parser("impact")
    impact.add_argument("--out", type=Path, default=DEFAULT_OUT)
    impact.add_argument("--base", default="origin/main")
    impact.add_argument("paths", nargs="*")
    query = sub.add_parser("query")
    query.add_argument("--out", type=Path, default=DEFAULT_OUT)
    query.add_argument("--kind", choices=["file", "symbol", "deps", "rdeps", "subsystem"], required=True)
    query.add_argument("--value", required=True)
    query.add_argument("--transitive", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--out", type=Path, default=DEFAULT_OUT)
    dep = sub.add_parser("dependabot-notes")
    dep.add_argument("--alerts", type=Path)
    dep.add_argument("--prs", type=Path)
    dep.add_argument("--out", type=Path, default=DEFAULT_OUT / "dependabot-notes.md")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            snapshot_command(args.out, args.base)
        elif args.command == "check":
            check_contracts()
            if args.gate:
                base.note_gate(args.base)
        elif args.command == "gate":
            check_contracts()
            base.note_gate(args.base)
        elif args.command == "impact":
            impact_command(args.out, args.base, args.paths)
        elif args.command == "query":
            query_command(args.out, args.kind, args.value, args.transitive)
        elif args.command == "doctor":
            return doctor_command(args.out)
        elif args.command == "dependabot-notes":
            base.dependabot_notes(args.alerts, args.prs, args.out)
        return 0
    except RuntimeError as exc:
        print(f"repo-intel-sota: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
