#!/usr/bin/env python3
"""Deep deterministic enrichment for the repository intelligence graph.

This layer stays stdlib-only and intentionally consumes the existing Git-backed
snapshot instead of rescanning the repository independently. It adds the pieces
needed for build/agent decisions that a source-only graph cannot answer:

- direct package/dependency inventory across Python, npm, Docker and Actions;
- workflow/build-target references to scripts, tests and manifests;
- API/frontend route and environment-variable surfaces without secret values;
- deterministic Git-history churn/freshness and graph-centrality hotspots;
- batch evidence state derived from handoff notes (never inferred completion);
- compact agent search records and changed-file status summaries.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Iterable

import repo_intel as base

ROOT = base.ROOT
TEXT_LIMIT = 2 * 1024 * 1024
HISTORY_COMMITS = 600

_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(.*)$")
_FASTAPI_ROUTE_RE = re.compile(
    r"@(?:[A-Za-z_][\w]*\.)?(get|post|put|patch|delete|options|head|websocket)\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_ENV_PATTERNS = (
    re.compile(r"\bos\.getenv\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']"),
    re.compile(r"\bos\.environ(?:\.get)?\(?\s*\[?\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']"),
    re.compile(r"\bprocess\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bprocess\.env\[\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\]"),
)
_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.@+\-]+)+\.(?:py|sh|json|toml|ya?ml|lock|txt))"
)
_PY_MODULE_RE = re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
_MAKE_TARGET_RE = re.compile(r"\bmake\s+([A-Za-z0-9_.-]+)")
_ACTION_USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
_BATCH_RE = re.compile(r"\bB\d{3}\b")


def _read_text(path: str) -> str | None:
    target = ROOT / path
    try:
        if target.stat().st_size > TEXT_LIMIT:
            return None
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _json(path: str) -> Any:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalise_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower()).strip("-")


def _requirement_name(spec: str) -> tuple[str, str] | None:
    candidate = spec.strip()
    if not candidate or candidate.startswith(("#", "-", "git+", "http://", "https://")):
        return None
    candidate = candidate.split(";", 1)[0].strip()
    if " @ " in candidate:
        name, requirement = candidate.split(" @ ", 1)
        return name.strip(), "@ " + requirement.strip()
    match = _REQ_NAME_RE.match(candidate)
    if not match:
        return None
    name = match.group(1).split("[", 1)[0]
    return name, match.group(2).strip()


def dependency_inventory(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Parse direct dependency declarations without resolving the network."""
    packages: list[dict[str, Any]] = []
    scripts: list[dict[str, str]] = []
    paths = {row["path"] for row in snapshot["files"]}

    def add(ecosystem: str, name: str, requirement: str, manifest: str, scope: str) -> None:
        packages.append(
            {
                "ecosystem": ecosystem,
                "name": name,
                "normalised_name": _normalise_package(name),
                "requirement": requirement,
                "manifest": manifest,
                "scope": scope,
                "relationship": "direct-declaration",
            }
        )

    for path in sorted(paths):
        name = Path(path).name
        if name == "pyproject.toml":
            text = _read_text(path)
            if text is None:
                continue
            try:
                payload = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                continue
            project = payload.get("project", {}) if isinstance(payload, dict) else {}
            for spec in project.get("dependencies", []) or []:
                parsed = _requirement_name(str(spec))
                if parsed:
                    add("pypi", parsed[0], parsed[1], path, "runtime")
            optional = project.get("optional-dependencies", {}) or {}
            if isinstance(optional, dict):
                for group, specs in optional.items():
                    for spec in specs or []:
                        parsed = _requirement_name(str(spec))
                        if parsed:
                            add("pypi", parsed[0], parsed[1], path, f"optional:{group}")
            build_system = payload.get("build-system", {}) if isinstance(payload, dict) else {}
            for spec in build_system.get("requires", []) or []:
                parsed = _requirement_name(str(spec))
                if parsed:
                    add("pypi", parsed[0], parsed[1], path, "build")

        elif name.startswith("requirements") and name.endswith(".txt"):
            text = _read_text(path)
            if text is None:
                continue
            scope = "development" if any(token in name for token in ("dev", "test")) else "runtime"
            for line in text.splitlines():
                parsed = _requirement_name(line)
                if parsed:
                    add("pypi", parsed[0], parsed[1], path, scope)

        elif name == "package.json":
            payload = _json(path)
            if not isinstance(payload, dict):
                continue
            for section, scope in (
                ("dependencies", "runtime"),
                ("devDependencies", "development"),
                ("peerDependencies", "peer"),
                ("optionalDependencies", "optional"),
            ):
                deps = payload.get(section, {}) or {}
                if isinstance(deps, dict):
                    for dep_name, requirement in deps.items():
                        add("npm", str(dep_name), str(requirement), path, scope)
            package_scripts = payload.get("scripts", {}) or {}
            if isinstance(package_scripts, dict):
                for script_name, command in package_scripts.items():
                    scripts.append(
                        {
                            "kind": "npm-script",
                            "manifest": path,
                            "name": str(script_name),
                            "command": str(command),
                        }
                    )

        elif name.lower() == "dockerfile" or name.lower().startswith("dockerfile."):
            text = _read_text(path)
            if text is None:
                continue
            for match in re.finditer(r"^\s*FROM\s+([^\s]+)", text, re.IGNORECASE | re.MULTILINE):
                image = match.group(1)
                add("docker", image.split("@", 1)[0], image, path, "base-image")

        elif path.startswith(".github/workflows/") and Path(path).suffix.lower() in {".yml", ".yaml"}:
            text = _read_text(path)
            if text is None:
                continue
            for match in _ACTION_USES_RE.finditer(text):
                spec = match.group(1)
                if spec.startswith(("./", "docker://")):
                    continue
                action, _, ref = spec.partition("@")
                add("github-actions", action, ref, path, "workflow-action")

    deduped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for item in packages:
        key = (
            item["ecosystem"],
            item["normalised_name"],
            item["manifest"],
            item["scope"],
            item["requirement"],
        )
        deduped[key] = item
    packages = sorted(
        deduped.values(),
        key=lambda item: (item["ecosystem"], item["normalised_name"], item["manifest"], item["scope"]),
    )
    ecosystems: dict[str, int] = defaultdict(int)
    for item in packages:
        ecosystems[item["ecosystem"]] += 1
    return {
        "schema": 1,
        "packages": packages,
        "package_count": len(packages),
        "ecosystems": dict(sorted(ecosystems.items())),
        "package_scripts": sorted(scripts, key=lambda item: (item["manifest"], item["name"])),
        "semantics": "Direct declarations only; this offline index does not claim transitive resolution or vulnerability state.",
    }


def _expo_route(path: str) -> str | None:
    if not path.startswith("frontend/app/"):
        return None
    suffix = Path(path).suffix.lower()
    if suffix not in {".js", ".jsx", ".ts", ".tsx"}:
        return None
    rel = Path(path).relative_to("frontend/app").with_suffix("")
    parts: list[str] = []
    for part in rel.parts:
        if part == "_layout" or (part.startswith("(") and part.endswith(")")):
            continue
        if part == "index":
            continue
        if part.startswith("[[...") and part.endswith("]]" ):
            parts.append("*" + part[5:-2])
        elif part.startswith("[...") and part.endswith("]"):
            parts.append("*" + part[4:-1])
        elif part.startswith("[") and part.endswith("]"):
            parts.append(":" + part[1:-1])
        else:
            parts.append(part)
    return "/" + "/".join(parts)


def surface_inventory(snapshot: dict[str, Any]) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    env_refs: dict[str, set[str]] = defaultdict(set)
    documented_env: set[str] = set()

    for row in snapshot["files"]:
        path = row["path"]
        route = _expo_route(path)
        if route is not None:
            routes.append({"kind": "expo-file-route", "method": "screen", "route": route, "path": path})

        text = _read_text(path)
        if text is None:
            continue
        if Path(path).name == ".env.example":
            for line in text.splitlines():
                candidate = line.strip()
                if not candidate or candidate.startswith("#") or "=" not in candidate:
                    continue
                key = candidate.split("=", 1)[0].strip()
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    documented_env.add(key)
        if Path(path).suffix.lower() == ".py":
            for match in _FASTAPI_ROUTE_RE.finditer(text):
                routes.append(
                    {
                        "kind": "python-http-route",
                        "method": match.group(1).upper(),
                        "route": match.group(2),
                        "path": path,
                        "precision": "lexical-decorator",
                    }
                )
        if Path(path).suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx"}:
            for pattern in _ENV_PATTERNS:
                for match in pattern.finditer(text):
                    env_refs[match.group(1)].add(path)

    env = [
        {
            "name": name,
            "documented_in_example": name in documented_env,
            "references": sorted(paths),
            "reference_count": len(paths),
        }
        for name, paths in sorted(env_refs.items())
    ]
    route_seen: set[tuple[str, str, str]] = set()
    deduped_routes: list[dict[str, Any]] = []
    for route in routes:
        key = (str(route["method"]), str(route["route"]), str(route["path"]))
        if key not in route_seen:
            route_seen.add(key)
            deduped_routes.append(route)
    deduped_routes.sort(key=lambda item: (item["route"], item["method"], item["path"]))
    return {
        "schema": 1,
        "routes": deduped_routes,
        "route_count": len(deduped_routes),
        "environment_variables": env,
        "environment_variable_count": len(env),
        "undocumented_environment_variables": [item["name"] for item in env if not item["documented_in_example"]],
        "security_note": "Environment-variable names and reference paths are indexed; values are never emitted.",
    }


def _module_paths(snapshot: dict[str, Any]) -> dict[str, str]:
    modules: dict[str, str] = {}
    for row in snapshot["files"]:
        path = row["path"]
        if Path(path).suffix.lower() not in {".py", ".pyi"}:
            continue
        parts = list(Path(path).with_suffix("").parts)
        if parts and parts[-1] in {"__init__", "__main__"}:
            module_parts = parts[:-1]
            if module_parts:
                modules[".".join(module_parts)] = path
        if parts:
            modules[".".join(parts)] = path
    return modules


def _file_references(text: str, paths: set[str], modules: dict[str, str]) -> set[str]:
    refs = {match.group(1) for match in _PATH_TOKEN_RE.finditer(text) if match.group(1) in paths}
    for match in _PY_MODULE_RE.finditer(text):
        module = match.group(1)
        if module in modules:
            refs.add(modules[module])
        elif module + ".__main__" in modules:
            refs.add(modules[module + ".__main__"])
    return refs


def build_relationships(snapshot: dict[str, Any], dependencies: dict[str, Any]) -> dict[str, Any]:
    paths = {row["path"] for row in snapshot["files"]}
    modules = _module_paths(snapshot)
    edges: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    build_targets: list[dict[str, Any]] = []

    for row in snapshot["files"]:
        path = row["path"]
        if not row.get("flags", {}).get("workflow"):
            continue
        text = _read_text(path)
        if text is None:
            continue
        for target in sorted(_file_references(text, paths, modules)):
            if target != path:
                edges.append(
                    {"from": f"file:{path}", "to": f"file:{target}", "type": "workflow-uses", "precision": "lexical"}
                )
        for match in _MAKE_TARGET_RE.finditer(text):
            target_id = f"target:make:{match.group(1)}"
            nodes.append({"id": target_id, "type": "build-target", "kind": "make", "name": match.group(1)})
            edges.append({"from": f"file:{path}", "to": target_id, "type": "invokes", "precision": "lexical"})

    makefile = _read_text("Makefile") if "Makefile" in paths else None
    if makefile:
        current: str | None = None
        command_lines: list[str] = []

        def flush() -> None:
            nonlocal current, command_lines
            if current is None:
                return
            command = "\n".join(command_lines).strip()
            target_id = f"target:make:{current}"
            nodes.append({"id": target_id, "type": "build-target", "kind": "make", "name": current})
            refs = sorted(_file_references(command, paths, modules))
            build_targets.append({"id": target_id, "name": current, "command": command, "references": refs})
            edges.append({"from": "file:Makefile", "to": target_id, "type": "declares-target", "precision": "structural"})
            for ref in refs:
                edges.append({"from": target_id, "to": f"file:{ref}", "type": "build-uses", "precision": "lexical"})
            current = None
            command_lines = []

        for line in makefile.splitlines():
            if line and not line.startswith((" ", "\t", ".")) and ":" in line:
                match = re.match(r"^([A-Za-z0-9_.-]+)\s*:", line)
                if match:
                    flush()
                    current = match.group(1)
                    continue
            if current is not None and line.startswith("\t"):
                command_lines.append(line.strip())
        flush()

    for item in dependencies["packages"]:
        package_id = f"package:{item['ecosystem']}:{item['normalised_name']}"
        nodes.append(
            {
                "id": package_id,
                "type": "package",
                "ecosystem": item["ecosystem"],
                "name": item["name"],
            }
        )
        edges.append(
            {
                "from": f"file:{item['manifest']}",
                "to": package_id,
                "type": "declares-dependency",
                "precision": "manifest",
            }
        )

    seen_edges: set[tuple[str, str, str]] = set()
    deduped_edges: list[dict[str, Any]] = []
    for edge in edges:
        key = (edge["from"], edge["to"], edge["type"])
        if key not in seen_edges:
            seen_edges.add(key)
            deduped_edges.append(edge)
    nodes_by_id = {node["id"]: node for node in nodes}
    return {
        "schema": 1,
        "nodes": [nodes_by_id[key] for key in sorted(nodes_by_id)],
        "edges": sorted(deduped_edges, key=lambda edge: (edge["from"], edge["to"], edge["type"])),
        "build_targets": sorted(build_targets, key=lambda item: item["name"]),
    }


def _parse_history(output: str, paths: set[str]) -> tuple[int, dict[str, dict[str, int]]]:
    touches: dict[str, int] = defaultdict(int)
    last_changed: dict[str, int] = {}
    current_ts = 0
    commits = 0
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("@@"):
            commits += 1
            try:
                current_ts = int(line[2:])
            except ValueError:
                current_ts = 0
            continue
        if not line or line not in paths:
            continue
        touches[line] += 1
        if current_ts and current_ts > last_changed.get(line, 0):
            last_changed[line] = current_ts
    return commits, {
        path: {"touches": touches.get(path, 0), "last_changed_epoch": last_changed.get(path, 0)}
        for path in paths
    }


def history_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    paths = {row["path"] for row in snapshot["files"]}
    output = base.git(
        "log",
        "-n",
        str(HISTORY_COMMITS),
        "--format=@@%ct",
        "--name-only",
        "--no-renames",
        check=False,
    )
    commits, metrics = _parse_history(output, paths)
    head_text = base.git("log", "-1", "--format=%ct", check=False).strip()
    try:
        head_epoch = int(head_text)
    except ValueError:
        head_epoch = 0
    for item in metrics.values():
        last_changed = item["last_changed_epoch"]
        item["age_days_at_head"] = round(max(0, head_epoch - last_changed) / 86400, 2) if last_changed else None
    return {
        "schema": 1,
        "window_commits_requested": HISTORY_COMMITS,
        "window_commits_observed": commits,
        "head_epoch": head_epoch,
        "files": metrics,
        "semantics": "Touch/freshness data is deterministic relative to repository HEAD and the bounded Git history window.",
    }


def _centrality(snapshot: dict[str, Any], extra_edges: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    allowed = {"imports", "tests", "workflow-uses", "build-uses"}
    for edge in [*snapshot["graph"]["edges"], *extra_edges]:
        if edge["type"] not in allowed:
            continue
        source = edge["from"]
        target = edge["to"]
        if source.startswith("file:") and target.startswith("file:"):
            outgoing[source].add(target)
            incoming[target].add(source)
    result: dict[str, dict[str, int]] = {}
    for row in snapshot["files"]:
        node = f"file:{row['path']}"
        result[row["path"]] = {"fan_in": len(incoming[node]), "fan_out": len(outgoing[node])}
    return result


def hotspot_inventory(
    snapshot: dict[str, Any], history: dict[str, Any], extra_edges: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    centrality = _centrality(snapshot, extra_edges)
    raw_scores: dict[str, float] = {}
    components: dict[str, dict[str, Any]] = {}
    for row in snapshot["files"]:
        path = row["path"]
        hist = history["files"].get(path, {})
        graph = centrality.get(path, {"fan_in": 0, "fan_out": 0})
        touch = math.log1p(int(hist.get("touches", 0)))
        fan_in = math.log1p(graph["fan_in"])
        fan_out = math.log1p(graph["fan_out"])
        size = math.log1p(max(0, int(row.get("size", 0)))) / 16.0
        risk = str((row.get("owner") or {}).get("risk", "unknown"))
        risk_boost = {"critical": 1.8, "high": 1.4, "medium": 1.15}.get(risk, 1.0)
        security_boost = 1.25 if row.get("flags", {}).get("security_sensitive") else 1.0
        raw = (touch * 1.9 + fan_in * 2.2 + fan_out + size) * risk_boost * security_boost
        raw_scores[path] = raw
        components[path] = {
            "touches": int(hist.get("touches", 0)),
            "age_days_at_head": hist.get("age_days_at_head"),
            "fan_in": graph["fan_in"],
            "fan_out": graph["fan_out"],
            "risk": risk,
            "security_sensitive": bool(row.get("flags", {}).get("security_sensitive")),
        }
    ceiling = max(raw_scores.values(), default=1.0) or 1.0
    hotspots = [
        {"path": path, "score": round(raw / ceiling * 100, 2), **components[path]}
        for path, raw in raw_scores.items()
    ]
    hotspots.sort(key=lambda item: (-item["score"], item["path"]))
    return {
        "schema": 1,
        "hotspots": hotspots[:250],
        "scoring_semantics": (
            "Relative triage score from bounded Git touches, file dependency degree, size, ownership risk and security sensitivity; "
            "it is not a code-quality grade."
        ),
    }


def batch_status(snapshot: dict[str, Any]) -> dict[str, Any]:
    batches = base.load_json("batches.json").get("batches", [])
    notes: dict[str, list[str]] = defaultdict(list)
    for row in snapshot["files"]:
        path = row["path"]
        if not path.startswith("repo-intel/notes/") or not path.endswith(".md"):
            continue
        text = _read_text(path) or ""
        for batch_id in sorted(set(_BATCH_RE.findall(text + " " + path))):
            notes[batch_id].append(path)
    evidence_ids = set(notes)
    result = []
    lane_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"planned": 0, "evidence-noted": 0})
    for batch in batches:
        batch_id = str(batch["id"])
        state = "evidence-noted" if batch_id in evidence_ids else "planned"
        deps = list(batch.get("depends_on", []))
        result.append(
            {
                **batch,
                "index_state": state,
                "evidence_notes": sorted(notes.get(batch_id, [])),
                "dependency_notes_present": [dep for dep in deps if dep in evidence_ids],
                "dependency_notes_missing": [dep for dep in deps if dep not in evidence_ids],
            }
        )
        lane_counts[str(batch["lane"])][state] += 1
    return {
        "schema": 1,
        "batches": result,
        "lane_counts": {lane: counts for lane, counts in sorted(lane_counts.items())},
        "semantics": (
            "evidence-noted means a handoff note references the batch. It does not mean complete, merged, correct, or SOTA-ready."
        ),
    }


def search_catalog(
    snapshot: dict[str, Any], surfaces: dict[str, Any], hotspots: dict[str, Any], dependencies: dict[str, Any]
) -> dict[str, Any]:
    routes_by_path: dict[str, list[str]] = defaultdict(list)
    for item in surfaces["routes"]:
        routes_by_path[item["path"]].append(f"{item['method']} {item['route']}")
    env_by_path: dict[str, list[str]] = defaultdict(list)
    for item in surfaces["environment_variables"]:
        for path in item["references"]:
            env_by_path[path].append(item["name"])
    hotspot_by_path = {item["path"]: item["score"] for item in hotspots["hotspots"]}
    packages_by_manifest: dict[str, list[str]] = defaultdict(list)
    for item in dependencies["packages"]:
        packages_by_manifest[item["manifest"]].append(f"{item['ecosystem']}:{item['name']}")
    semantic = snapshot.get("semantic", {})
    docs = []
    for row in snapshot["files"]:
        path = row["path"]
        rec = semantic.get(path, {})
        symbols = [str(item.get("qualified_name", "")) for item in rec.get("symbols", [])[:40]]
        imports = [str(item.get("module", "")) for item in rec.get("imports", [])[:40]]
        docs.append(
            {
                "path": path,
                "subsystem": row["subsystem"],
                "role": row["role"],
                "language": row.get("language"),
                "owner": row.get("owner"),
                "flags": row.get("flags", {}),
                "symbols": symbols,
                "imports": imports,
                "routes": sorted(routes_by_path.get(path, [])),
                "environment_variables": sorted(env_by_path.get(path, [])),
                "declared_packages": sorted(packages_by_manifest.get(path, [])),
                "hotspot_score": hotspot_by_path.get(path, 0.0),
            }
        )
    return {
        "schema": 1,
        "documents": docs,
        "document_count": len(docs),
        "semantics": "Compact deterministic retrieval records for agents; no embeddings or generated summaries are required to refresh them.",
    }


def search(catalog: dict[str, Any], query: str, limit: int = 50) -> list[dict[str, Any]]:
    tokens = [token for token in re.split(r"[^A-Za-z0-9_@.+/-]+", query.lower()) if token]
    ranked: list[tuple[float, dict[str, Any]]] = []
    for doc in catalog.get("documents", []):
        path = str(doc["path"]).lower()
        subsystem = str(doc.get("subsystem", "")).lower()
        symbols = " ".join(doc.get("symbols", [])).lower()
        imports = " ".join(doc.get("imports", [])).lower()
        routes = " ".join(doc.get("routes", [])).lower()
        env = " ".join(doc.get("environment_variables", [])).lower()
        packages = " ".join(doc.get("declared_packages", [])).lower()
        score = 0.0
        for token in tokens:
            score += 8.0 if token in path else 0.0
            score += 5.0 if token in symbols else 0.0
            score += 3.0 if token in routes else 0.0
            score += 2.5 if token in env or token in packages else 0.0
            score += 2.0 if token in imports else 0.0
            score += 1.0 if token in subsystem else 0.0
        if score:
            score += min(float(doc.get("hotspot_score", 0.0)) / 100.0, 1.0)
            ranked.append((score, doc))
    ranked.sort(key=lambda item: (-item[0], item[1]["path"]))
    return [{"score": round(score, 3), **doc} for score, doc in ranked[:limit]]


def change_set(base_ref: str, impact: dict[str, Any]) -> dict[str, Any]:
    raw = base.git("diff", "--name-status", "--find-renames", f"{base_ref}...HEAD", check=False)
    changes = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        code = parts[0]
        if code.startswith("R") and len(parts) >= 3:
            changes.append({"status": "renamed", "score": code[1:] or None, "from": parts[1], "path": parts[2]})
        elif len(parts) >= 2:
            status = {"A": "added", "M": "modified", "D": "deleted", "T": "type-changed"}.get(code[0], code)
            changes.append({"status": status, "path": parts[1]})
    return {
        "schema": 1,
        "base": base_ref,
        "changes": changes,
        "change_count": len(changes),
        "affected_file_count": impact.get("affected_file_count", 0),
        "candidate_tests": impact.get("candidate_tests", []),
        "affected_subsystems": impact.get("subsystems", []),
        "security_zones": impact.get("security_zones", []),
    }


def apply(snapshot: dict[str, Any]) -> dict[str, Any]:
    dependencies = dependency_inventory(snapshot)
    surfaces = surface_inventory(snapshot)
    relationships = build_relationships(snapshot, dependencies)
    history = history_metrics(snapshot)
    hotspots = hotspot_inventory(snapshot, history, relationships["edges"])
    batches = batch_status(snapshot)
    catalog = search_catalog(snapshot, surfaces, hotspots, dependencies)

    nodes_by_id = {node["id"]: node for node in snapshot["graph"]["nodes"]}
    for node in relationships["nodes"]:
        nodes_by_id[node["id"]] = node
    edge_by_key = {
        (edge["from"], edge["to"], edge["type"]): edge for edge in snapshot["graph"]["edges"]
    }
    for edge in relationships["edges"]:
        edge_by_key[(edge["from"], edge["to"], edge["type"])] = edge
    snapshot["graph"]["nodes"] = [nodes_by_id[key] for key in sorted(nodes_by_id)]
    snapshot["graph"]["edges"] = [edge_by_key[key] for key in sorted(edge_by_key)]
    reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in snapshot["graph"]["edges"]:
        reverse[edge["to"]].append(
            {"from": edge["from"], "type": edge["type"], "precision": edge.get("precision", "unknown")}
        )
    snapshot["graph"]["reverse_edges"] = {
        key: sorted(value, key=lambda item: (item["from"], item["type"])) for key, value in sorted(reverse.items())
    }

    history_by_path = history["files"]
    centrality = _centrality(snapshot, [])
    hotspot_by_path = {item["path"]: item for item in hotspots["hotspots"]}
    for row in snapshot["files"]:
        row["history"] = history_by_path.get(row["path"], {})
        row["centrality"] = centrality.get(row["path"], {"fan_in": 0, "fan_out": 0})
        row["hotspot_score"] = hotspot_by_path.get(row["path"], {}).get("score", 0.0)

    snapshot["schema"] = 4
    snapshot["metrics"].update(
        {
            "graph_nodes": len(snapshot["graph"]["nodes"]),
            "graph_edges": len(snapshot["graph"]["edges"]),
            "declared_dependency_count": dependencies["package_count"],
            "route_count": surfaces["route_count"],
            "environment_variable_count": surfaces["environment_variable_count"],
            "undocumented_environment_variable_count": len(surfaces["undocumented_environment_variables"]),
            "build_target_count": len(relationships["build_targets"]),
            "history_window_commits": history["window_commits_observed"],
            "search_document_count": catalog["document_count"],
        }
    )
    return {
        "dependencies": dependencies,
        "surfaces": surfaces,
        "relationships": relationships,
        "history": history,
        "hotspots": hotspots,
        "batch_status": batches,
        "search_catalog": catalog,
    }


def check_contracts() -> None:
    contract = base.CONFIG_DIR / "deep-index-contract.json"
    if not contract.is_file():
        raise RuntimeError("missing SOTA repo-intel contract: deep-index-contract.json")
    payload = json.loads(contract.read_text(encoding="utf-8"))
    required = {
        "dependencies.json",
        "surfaces.json",
        "hotspots.json",
        "batch-status.json",
        "search-catalog.json",
        "change-set.json",
    }
    outputs = set(payload.get("generated_outputs", []))
    if not required.issubset(outputs):
        raise RuntimeError("deep-index-contract.json missing frontier generated outputs")
    if int(payload.get("history_window_commits", 0)) != HISTORY_COMMITS:
        raise RuntimeError("deep-index history window contract drifted")
    print(f"repo-intel-deep: contract valid ({len(required)} frontier outputs, history={HISTORY_COMMITS} commits)")


if __name__ == "__main__":
    print("repo_intel_deep is a library layer; use scripts/repo_intel_frontier.py", file=sys.stderr)
    raise SystemExit(2)
