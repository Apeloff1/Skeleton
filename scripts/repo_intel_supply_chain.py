#!/usr/bin/env python3
"""Structured dependency, CODEOWNERS, workflow and architecture graph extension.

This module is stdlib-only and is designed to compose with repo_intel_sota.py.
It does not install dependencies or execute repository code while indexing.
"""
from __future__ import annotations

from collections import defaultdict
import fnmatch
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Iterable

import repo_intel as base

ROOT = base.ROOT

_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_DOCKER_FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)", re.IGNORECASE)
_WORKFLOW_USES_RE = re.compile(r"^\s*-?\s*uses:\s*['\"]?([^\s'\"]+)", re.MULTILINE)


def _read_text(path: str) -> str | None:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _dep(ecosystem: str, name: str, spec: str, scope: str, source: str) -> dict[str, str]:
    return {
        "ecosystem": ecosystem,
        "name": name,
        "spec": spec,
        "scope": scope,
        "source": source,
        "id": f"dependency:{ecosystem}:{name.lower()}",
    }


def parse_requirements(path: str, text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(("-r ", "--requirement ", "--index-url", "--extra-index-url")):
            continue
        if line.startswith(("git+", "http://", "https://")):
            deps.append(_dep("pypi", line, line, "runtime", path))
            continue
        match = _REQ_NAME_RE.match(line)
        if match:
            name = match.group(1)
            deps.append(_dep("pypi", name, line[len(name):].strip(), "runtime", path))
    return deps


def parse_pyproject(path: str, text: str) -> list[dict[str, str]]:
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    deps: list[dict[str, str]] = []
    project = payload.get("project") or {}
    for raw in project.get("dependencies") or []:
        match = _REQ_NAME_RE.match(str(raw))
        if match:
            name = match.group(1)
            deps.append(_dep("pypi", name, str(raw)[len(name):].strip(), "runtime", path))
    for group, items in (project.get("optional-dependencies") or {}).items():
        for raw in items or []:
            match = _REQ_NAME_RE.match(str(raw))
            if match:
                name = match.group(1)
                deps.append(_dep("pypi", name, str(raw)[len(name):].strip(), f"optional:{group}", path))
    for raw in (payload.get("build-system") or {}).get("requires") or []:
        match = _REQ_NAME_RE.match(str(raw))
        if match:
            name = match.group(1)
            deps.append(_dep("pypi", name, str(raw)[len(name):].strip(), "build", path))
    return deps


def parse_package_json(path: str, text: str) -> list[dict[str, str]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    deps: list[dict[str, str]] = []
    sections = {
        "dependencies": "runtime",
        "devDependencies": "development",
        "peerDependencies": "peer",
        "optionalDependencies": "optional",
        "resolutions": "resolution",
    }
    for section, scope in sections.items():
        for name, spec in (payload.get(section) or {}).items():
            deps.append(_dep("npm", str(name), str(spec), scope, path))
    return deps


def parse_dockerfile(path: str, text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _DOCKER_FROM_RE.match(line)
        if not match:
            continue
        image = match.group(1)
        if image.lower() == "scratch":
            continue
        name = image.split("@", 1)[0].split(":", 1)[0]
        spec = image[len(name):]
        deps.append(_dep("oci", name, spec, "base-image", path))
    return deps


def parse_workflow_actions(path: str, text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for match in _WORKFLOW_USES_RE.finditer(text):
        value = match.group(1)
        if value.startswith("./"):
            continue
        name, _, spec = value.partition("@")
        deps.append(_dep("github-actions", name, f"@{spec}" if spec else "", "workflow-action", path))
    return deps


def dependency_records(files: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in files:
        path = str(row["path"])
        name = Path(path).name.lower()
        text: str | None = None
        parser = None
        if name == "pyproject.toml":
            parser = parse_pyproject
        elif name.startswith("requirements") and name.endswith((".txt", ".in")):
            parser = parse_requirements
        elif name == "package.json":
            parser = parse_package_json
        elif name == "dockerfile" or name.startswith("dockerfile."):
            parser = parse_dockerfile
        elif path.startswith(".github/workflows/") and Path(path).suffix.lower() in {".yml", ".yaml"}:
            parser = parse_workflow_actions
        if parser is None:
            continue
        text = _read_text(path)
        if text is not None:
            records.extend(parser(path, text))

    # Deduplicate while preserving source/scope distinctions.
    unique: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for item in records:
        key = (item["ecosystem"], item["name"].lower(), item["spec"], item["scope"], item["source"])
        unique[key] = item
    return sorted(unique.values(), key=lambda d: (d["ecosystem"], d["name"].lower(), d["source"], d["scope"], d["spec"]))


def supply_chain_graph(files: list[dict[str, Any]]) -> dict[str, Any]:
    records = dependency_records(files)
    by_component: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    for item in records:
        node = by_component.setdefault(
            item["id"],
            {
                "id": item["id"],
                "type": "external-dependency",
                "ecosystem": item["ecosystem"],
                "name": item["name"],
                "specs": set(),
                "scopes": set(),
                "sources": set(),
            },
        )
        node["specs"].add(item["spec"])
        node["scopes"].add(item["scope"])
        node["sources"].add(item["source"])
        edges.append({
            "from": f"file:{item['source']}",
            "to": item["id"],
            "type": "declares-dependency",
            "precision": "manifest",
            "scope": item["scope"],
            "spec": item["spec"],
        })
    nodes = []
    for node in by_component.values():
        nodes.append({
            **node,
            "specs": sorted(node["specs"]),
            "scopes": sorted(node["scopes"]),
            "sources": sorted(node["sources"]),
        })
    edges.sort(key=lambda e: (e["from"], e["to"], e["scope"], e["spec"]))
    nodes.sort(key=lambda n: (n["ecosystem"], n["name"].lower()))
    ecosystem_counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        ecosystem_counts[node["ecosystem"]] += 1
    return {
        "schema": 1,
        "nodes": nodes,
        "edges": edges,
        "component_count": len(nodes),
        "declaration_count": len(edges),
        "ecosystems": dict(sorted(ecosystem_counts.items())),
    }


def find_codeowners() -> str | None:
    for candidate in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        if (ROOT / candidate).is_file():
            return candidate
    return None


def parse_codeowners(path: str, text: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        owners = [item for item in parts[1:] if item.startswith("@")]
        if owners:
            rules.append({"pattern": pattern, "owners": owners, "line": line_number})
    return rules


def codeowners_inventory(files: list[dict[str, Any]]) -> dict[str, Any]:
    path = find_codeowners()
    if path is None:
        return {
            "schema": 1,
            "source": None,
            "rules": [],
            "matched_files": 0,
            "unmatched_files": len(files),
            "note": "No CODEOWNERS file is present; architectural ownership zones remain available separately.",
        }
    text = _read_text(path) or ""
    rules = parse_codeowners(path, text)
    matched = 0
    file_owners: dict[str, list[str]] = {}
    for row in files:
        candidate = str(row["path"])
        owners: list[str] | None = None
        # Approximation suitable for index hints. GitHub remains authoritative for exact CODEOWNERS matching semantics.
        for rule in rules:
            pattern = str(rule["pattern"])
            normalized = pattern.lstrip("/")
            if normalized.endswith("/"):
                normalized += "*"
            if fnmatch.fnmatch(candidate, normalized) or fnmatch.fnmatch("/" + candidate, pattern):
                owners = list(rule["owners"])
        if owners:
            matched += 1
            file_owners[candidate] = owners
    return {
        "schema": 1,
        "source": path,
        "rules": rules,
        "matched_files": matched,
        "unmatched_files": len(files) - matched,
        "file_owners": file_owners,
        "precision": "approximate-local-match; GitHub is authoritative for exact CODEOWNERS semantics",
    }


def boundary_violations(snapshot: dict[str, Any], rules_payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_path = {str(row["path"]): row for row in snapshot.get("files", [])}
    violations: list[dict[str, Any]] = []
    for edge in snapshot.get("graph", {}).get("edges", []):
        if not str(edge.get("from", "")).startswith("file:") or not str(edge.get("to", "")).startswith("file:"):
            continue
        source_path = str(edge["from"])[5:]
        target_path = str(edge["to"])[5:]
        source = by_path.get(source_path)
        target = by_path.get(target_path)
        if not source or not target:
            continue
        for rule in rules_payload.get("rules", []):
            if edge.get("type") not in rule.get("edge_types", []):
                continue
            if source.get("subsystem") not in rule.get("from_subsystems", []):
                continue
            if target.get("subsystem") not in rule.get("deny_to_subsystems", []):
                continue
            violations.append({
                "rule": rule["id"],
                "severity": rule.get("severity", "medium"),
                "source": source_path,
                "target": target_path,
                "edge_type": edge.get("type"),
                "precision": edge.get("precision", "unknown"),
                "reason": rule.get("reason", ""),
            })
    return sorted(violations, key=lambda v: (v["severity"], v["rule"], v["source"], v["target"]))


def augment_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    supply = supply_chain_graph(snapshot["files"])
    owners = codeowners_inventory(snapshot["files"])
    boundary_rules = base.load_json("boundaries.json")
    violations = boundary_violations(snapshot, boundary_rules)

    graph = snapshot.setdefault("graph", {})
    graph.setdefault("nodes", []).extend(supply["nodes"])
    graph.setdefault("edges", []).extend(supply["edges"])
    # Rebuild reverse map to include external dependencies.
    reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        reverse[str(edge["to"])].append({
            "from": str(edge["from"]),
            "type": str(edge["type"]),
            "precision": str(edge.get("precision", "unknown")),
        })
    graph["reverse_edges"] = {
        key: sorted(value, key=lambda x: (x["from"], x["type"]))
        for key, value in sorted(reverse.items())
    }
    graph["architecture_boundary_violations"] = violations

    snapshot["supply_chain"] = supply
    snapshot["codeowners"] = owners
    metrics = snapshot.setdefault("metrics", {})
    metrics["external_dependency_components"] = supply["component_count"]
    metrics["external_dependency_declarations"] = supply["declaration_count"]
    metrics["codeowners_matched_files"] = owners["matched_files"]
    metrics["architecture_boundary_violations"] = len(violations)
    metrics["graph_nodes"] = len(graph.get("nodes", []))
    metrics["graph_edges"] = len(graph.get("edges", []))
    return snapshot
