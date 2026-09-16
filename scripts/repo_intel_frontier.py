#!/usr/bin/env python3
"""Frontier repository intelligence entrypoint.

Composes the fast Git index, semantic graph, and deep build/supply-chain layer
into one deterministic machine interface. The core refresh requires no network.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sys
from typing import Any

import repo_intel as base
import repo_intel_deep as deep
import repo_intel_sota as sota

DEFAULT_OUT = base.DEFAULT_OUT


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _frontier_notes(
    snapshot: dict[str, Any],
    gaps: dict[str, Any],
    security_quality: dict[str, Any],
    impact: dict[str, Any],
    bundle: dict[str, Any],
) -> str:
    notes = base.render_notes(snapshot, gaps, security_quality)
    metrics = snapshot["metrics"]
    hot = bundle["hotspots"]["hotspots"][:8]
    batch_counts = bundle["batch_status"]["lane_counts"]
    evidence_noted = sum(counts.get("evidence-noted", 0) for counts in batch_counts.values())
    lines = [
        notes.rstrip(),
        "",
        "## Frontier index health",
        "",
        f"- Knowledge graph: **{metrics['graph_nodes']} nodes / {metrics['graph_edges']} edges**.",
        f"- Semantic cache hit ratio this run: **{metrics['semantic_cache_hit_ratio']:.1%}**.",
        f"- Declared dependency records: **{metrics['declared_dependency_count']}** across "
        f"{len(bundle['dependencies']['ecosystems'])} ecosystems.",
        f"- Indexed creator/runtime routes: **{metrics['route_count']}**.",
        f"- Environment-variable names referenced: **{metrics['environment_variable_count']}**; "
        f"**{metrics['undocumented_environment_variable_count']}** are not present in tracked `.env.example` files.",
        f"- Build targets indexed: **{metrics['build_target_count']}**.",
        f"- Deterministic churn window: **{metrics['history_window_commits']} Git commits**.",
        f"- Current reverse impact: **{impact['affected_file_count']} files**, "
        f"**{len(impact['subsystems'])} subsystems**, **{len(impact['candidate_tests'])} candidate tests**.",
        f"- Batch handoff evidence: **{evidence_noted}/100 batches referenced by notes**. "
        "This is evidence presence, not completion.",
        "",
        "## Highest-attention repository hotspots",
        "",
    ]
    for item in hot:
        lines.append(
            f"- `{item['path']}` — score **{item['score']}**, touches={item['touches']}, "
            f"fan-in={item['fan_in']}, fan-out={item['fan_out']}, risk={item['risk']}."
        )
    if not hot:
        lines.append("- No hotspot records generated.")
    lines.extend(
        [
            "",
            "Hotspot scores are relative triage signals, not quality grades. Dependency declarations are offline direct "
            "inventory, not a substitute for GitHub Dependency Graph/Dependabot vulnerability resolution.",
            "",
        ]
    )
    return "\n".join(lines)


def snapshot_command(out: Path, base_ref: str = "origin/main") -> dict[str, Any]:
    check_contracts()
    out.mkdir(parents=True, exist_ok=True)

    snapshot = sota.enrich_snapshot(base.build_snapshot(), out)
    bundle = deep.apply(snapshot)
    gaps = base.feature_gaps(snapshot)
    security_quality = base.security_quality(snapshot)
    build_map = sota._build_map(snapshot)
    build_map.update(
        {
            "schema": 4,
            "declared_dependency_count": bundle["dependencies"]["package_count"],
            "dependency_ecosystems": bundle["dependencies"]["ecosystems"],
            "build_targets": bundle["relationships"]["build_targets"],
            "route_count": bundle["surfaces"]["route_count"],
            "environment_variable_count": bundle["surfaces"]["environment_variable_count"],
            "hotspots": bundle["hotspots"]["hotspots"][:50],
        }
    )
    changed = base.changed_paths(base_ref)
    impact = sota._impact_from_paths(snapshot, changed)
    change_set = deep.change_set(base_ref, impact)

    _write_json(out / "index.json", snapshot)
    _write_json(out / "graph.json", snapshot["graph"])
    _write_json(out / "symbols.json", {"schema": 2, "symbols": snapshot["symbols"]})
    _write_json(out / "build-map.json", build_map)
    _write_json(out / "impact.json", impact)
    _write_json(out / "change-set.json", change_set)
    _write_json(out / "gaps.json", gaps)
    _write_json(out / "security-quality.json", security_quality)
    _write_json(out / "metrics.json", snapshot["metrics"])
    _write_json(out / "dependencies.json", bundle["dependencies"])
    _write_json(out / "surfaces.json", bundle["surfaces"])
    _write_json(out / "hotspots.json", bundle["hotspots"])
    _write_json(out / "batch-status.json", bundle["batch_status"])
    _write_json(out / "search-catalog.json", bundle["search_catalog"])
    _write_json(out / "history.json", bundle["history"])
    _write_json(out / "build-relationships.json", bundle["relationships"])
    (out / "notes.md").write_text(
        _frontier_notes(snapshot, gaps, security_quality, impact, bundle),
        encoding="utf-8",
    )

    print(
        "repo-intel-frontier: "
        f"{snapshot['tracked_files']} files, {snapshot['metrics']['graph_nodes']} nodes, "
        f"{snapshot['metrics']['graph_edges']} edges, {snapshot['metrics']['declared_dependency_count']} deps, "
        f"{snapshot['metrics']['route_count']} routes, "
        f"{snapshot['metrics']['semantic_cache_hit_ratio']:.1%} semantic cache hits"
    )
    return snapshot


def load_or_build(out: Path) -> dict[str, Any]:
    snapshot = _read_json(out / "index.json", None)
    if not isinstance(snapshot, dict) or int(snapshot.get("schema", 0)) < 4:
        snapshot = snapshot_command(out)
    return snapshot


def _traverse(snapshot: dict[str, Any], value: str, reverse: bool, transitive: bool) -> dict[str, Any]:
    start = f"file:{value}"
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if reverse:
        for target, incoming in snapshot["graph"]["reverse_edges"].items():
            adjacency[target].extend(incoming)
    else:
        for edge in snapshot["graph"]["edges"]:
            adjacency[edge["from"]].append(
                {"from": edge["to"], "type": edge["type"], "precision": edge.get("precision", "unknown")}
            )

    found: dict[str, set[str]] = defaultdict(set)
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for edge in adjacency.get(node, []):
            nxt = edge["from"]
            found[nxt].add(edge["type"])
            if transitive and nxt.startswith("file:") and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return {
        "start": value,
        "direction": "reverse" if reverse else "forward",
        "transitive": transitive,
        "nodes": [
            {"id": node, "edge_types": sorted(types)} for node, types in sorted(found.items())
        ],
    }


def query_command(out: Path, kind: str, value: str, transitive: bool, limit: int) -> None:
    snapshot = load_or_build(out)
    needle = value.lower()
    if kind == "file":
        row = next((item for item in snapshot["files"] if item["path"] == value), None)
        payload = {
            "file": row,
            "semantic": snapshot.get("semantic", {}).get(value),
            "forward": _traverse(snapshot, value, False, False),
            "reverse": _traverse(snapshot, value, True, False),
        }
    elif kind == "symbol":
        payload = {
            "symbols": [
                symbol
                for symbol in snapshot["symbols"]
                if needle in str(symbol.get("qualified_name", "")).lower()
            ][:limit]
        }
    elif kind == "deps":
        payload = _traverse(snapshot, value, False, transitive)
    elif kind == "rdeps":
        payload = _traverse(snapshot, value, True, transitive)
    elif kind == "subsystem":
        payload = {"files": [row for row in snapshot["files"] if row["subsystem"] == value][:limit]}
    elif kind == "dependency":
        data = _read_json(out / "dependencies.json", {"packages": []})
        payload = {
            "packages": [
                item
                for item in data.get("packages", [])
                if needle in str(item.get("name", "")).lower()
                or needle in str(item.get("ecosystem", "")).lower()
            ][:limit]
        }
    elif kind == "route":
        data = _read_json(out / "surfaces.json", {"routes": []})
        payload = {
            "routes": [
                item
                for item in data.get("routes", [])
                if needle in str(item.get("route", "")).lower()
                or needle in str(item.get("path", "")).lower()
            ][:limit]
        }
    elif kind == "env":
        data = _read_json(out / "surfaces.json", {"environment_variables": []})
        payload = {
            "environment_variables": [
                item
                for item in data.get("environment_variables", [])
                if needle in str(item.get("name", "")).lower()
            ][:limit]
        }
    elif kind == "hotspot":
        data = _read_json(out / "hotspots.json", {"hotspots": []})
        items = data.get("hotspots", [])
        payload = {"hotspots": [item for item in items if not value or needle in item["path"].lower()][:limit]}
    elif kind == "batch":
        data = _read_json(out / "batch-status.json", {"batches": []})
        payload = {
            "batches": [
                item
                for item in data.get("batches", [])
                if needle in str(item.get("id", "")).lower()
                or needle in str(item.get("lane", "")).lower()
                or needle in str(item.get("title", "")).lower()
            ][:limit]
        }
    elif kind == "search":
        catalog = _read_json(out / "search-catalog.json", {"documents": []})
        payload = {"results": deep.search(catalog, value, limit=limit)}
    else:
        raise RuntimeError(f"unsupported query kind: {kind}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def impact_command(out: Path, base_ref: str, paths: list[str]) -> None:
    snapshot = load_or_build(out)
    changed = sorted(set(paths or base.changed_paths(base_ref)))
    payload = sota._impact_from_paths(snapshot, changed)
    _write_json(out / "impact.json", payload)
    _write_json(out / "change-set.json", deep.change_set(base_ref, payload))
    print(json.dumps(payload, indent=2, sort_keys=True))


def doctor_command(out: Path) -> int:
    snapshot = load_or_build(out)
    metrics = snapshot["metrics"]
    blockers: list[str] = []
    advisories: list[str] = []
    if metrics.get("semantic_parse_failures"):
        blockers.append(f"semantic parse failures={metrics['semantic_parse_failures']}")
    if metrics.get("unowned_files"):
        advisories.append(f"unowned files={metrics['unowned_files']}")
    if metrics.get("dependency_cycles"):
        advisories.append(f"dependency cycles={metrics['dependency_cycles']}")
    if metrics.get("undocumented_environment_variable_count"):
        advisories.append(
            f"environment variables absent from tracked examples={metrics['undocumented_environment_variable_count']}"
        )
    if not snapshot.get("graph", {}).get("edges"):
        blockers.append("dependency graph has no edges")
    report = {
        "source_digest": snapshot["source_digest"],
        "healthy": not blockers,
        "blockers": blockers,
        "advisories": advisories,
        "metrics": metrics,
        "largest_cycles": snapshot["graph"].get("dependency_cycles", [])[:10],
        "top_hotspots": _read_json(out / "hotspots.json", {"hotspots": []}).get("hotspots", [])[:20],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not blockers else 1


def check_contracts() -> None:
    base.validate_configs()
    sota.check_contracts()
    deep.check_contracts()
    print("repo-intel-frontier: all layered contracts valid")


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
    query.add_argument(
        "--kind",
        choices=[
            "file",
            "symbol",
            "deps",
            "rdeps",
            "subsystem",
            "dependency",
            "route",
            "env",
            "hotspot",
            "batch",
            "search",
        ],
        required=True,
    )
    query.add_argument("--value", default="")
    query.add_argument("--transitive", action="store_true")
    query.add_argument("--limit", type=int, default=50)
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
            query_command(args.out, args.kind, args.value, args.transitive, max(1, min(args.limit, 500)))
        elif args.command == "doctor":
            return doctor_command(args.out)
        elif args.command == "dependabot-notes":
            base.dependabot_notes(args.alerts, args.prs, args.out)
        return 0
    except RuntimeError as exc:
        print(f"repo-intel-frontier: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
