#!/usr/bin/env python3
"""Canonical Skeleton repository knowledge-graph CLI.

Composes the fast Git index, semantic source graph, structured supply-chain graph,
ownership/boundary analysis, capability/security evidence, change impact, graph diff,
and agent handoff gates. Core indexing is network-free and stdlib-only.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sys
import time
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel as base  # noqa: E402
import repo_intel_sota as semantic  # noqa: E402
import repo_intel_supply_chain as supply  # noqa: E402

ROOT = base.ROOT
DEFAULT_OUT = base.DEFAULT_OUT


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def validate_contracts() -> None:
    semantic.check_contracts()
    required = ["boundaries.json"]
    missing = [name for name in required if not (base.CONFIG_DIR / name).is_file()]
    if missing:
        raise RuntimeError(f"missing canonical repo-index contracts: {', '.join(missing)}")
    boundaries = base.load_json("boundaries.json")
    ids = [rule["id"] for rule in boundaries.get("rules", [])]
    if len(ids) != len(set(ids)):
        raise RuntimeError("architecture boundary rule IDs must be unique")
    for rule in boundaries.get("rules", []):
        if not rule.get("from_subsystems") or not rule.get("deny_to_subsystems") or not rule.get("edge_types"):
            raise RuntimeError(f"architecture boundary rule is incomplete: {rule.get('id')}")
    print(f"repo-index: contracts valid ({len(ids)} architecture boundary rules)")


def build_snapshot(out: Path) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot = semantic.enrich_snapshot(base.build_snapshot(), out)
    snapshot = supply.augment_snapshot(snapshot)
    snapshot["schema"] = 4
    snapshot["metrics"]["canonical_snapshot_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return snapshot


def build_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    mapping = semantic._build_map(snapshot)
    mapping.update({
        "schema": 4,
        "external_dependencies": snapshot["supply_chain"]["component_count"],
        "dependency_ecosystems": snapshot["supply_chain"]["ecosystems"],
        "codeowners_source": snapshot["codeowners"].get("source"),
        "architecture_boundary_violations": snapshot["graph"].get("architecture_boundary_violations", []),
    })
    return mapping


def architecture_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    violations = snapshot["graph"].get("architecture_boundary_violations", [])
    by_severity: dict[str, int] = defaultdict(int)
    by_rule: dict[str, int] = defaultdict(int)
    for item in violations:
        by_severity[str(item.get("severity", "unknown"))] += 1
        by_rule[str(item.get("rule", "unknown"))] += 1
    return {
        "schema": 1,
        "violations": violations,
        "counts_by_severity": dict(sorted(by_severity.items())),
        "counts_by_rule": dict(sorted(by_rule.items())),
        "dependency_cycles": snapshot["graph"].get("dependency_cycles", []),
        "note": "Boundary findings are structural evidence. Existing violations should be baselined before fail-closed enforcement; new high-severity violations should require explicit justification.",
    }


def render_notes(snapshot: dict[str, Any], gaps: dict[str, Any], sq: dict[str, Any], impact: dict[str, Any]) -> str:
    text = base.render_notes(snapshot, gaps, sq)
    m = snapshot["metrics"]
    supply_graph = snapshot["supply_chain"]
    codeowners = snapshot["codeowners"]
    violations = snapshot["graph"].get("architecture_boundary_violations", [])
    lines = [
        text.rstrip(),
        "",
        "## Repository knowledge-graph health",
        "",
        f"- Graph: **{m['graph_nodes']} nodes / {m['graph_edges']} edges**.",
        f"- Semantic cache hit ratio this run: **{m['semantic_cache_hit_ratio']:.1%}**.",
        f"- Semantic parse failures: **{m['semantic_parse_failures']}**.",
        f"- Dependency cycles: **{m['dependency_cycles']}**.",
        f"- Architectural ownership coverage: **{m['owned_file_ratio']:.1%}**.",
        f"- External dependency components: **{supply_graph['component_count']}** across {', '.join(sorted(supply_graph['ecosystems'])) or 'no parsed ecosystems'}.",
        f"- Architecture boundary findings: **{len(violations)}**.",
        f"- CODEOWNERS: **{codeowners.get('source') or 'not present'}**; local matched files: **{codeowners.get('matched_files', 0)}**.",
        f"- Current reverse impact: **{impact['affected_file_count']} files / {len(impact['subsystems'])} subsystems / {len(impact['candidate_tests'])} candidate tests**.",
        "",
        "## Precision / evidence reminder",
        "",
        "- Python semantic edges are AST-derived; current JS/TS semantic edges are conservative lexical evidence.",
        "- Manifest dependency edges are structured-manifest evidence.",
        "- CODEOWNERS local matching is an approximation; GitHub is authoritative for exact ownership matching.",
        "- None of these layers independently proves correctness, security, release readiness, or SOTA performance.",
        "",
    ]
    return "\n".join(lines)


def snapshot_command(out: Path, base_ref: str) -> dict[str, Any]:
    validate_contracts()
    out.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot(out)
    gaps = base.feature_gaps(snapshot)
    sq = base.security_quality(snapshot)
    mapping = build_map(snapshot)
    changed = base.changed_paths(base_ref)
    impact = semantic._impact_from_paths(snapshot, changed)
    arch = architecture_report(snapshot)

    write_json(out / "index.json", snapshot)
    write_json(out / "graph.json", snapshot["graph"])
    write_json(out / "symbols.json", {"schema": 1, "symbols": snapshot["symbols"]})
    write_json(out / "build-map.json", mapping)
    write_json(out / "impact.json", impact)
    write_json(out / "gaps.json", gaps)
    write_json(out / "security-quality.json", sq)
    write_json(out / "metrics.json", snapshot["metrics"])
    write_json(out / "supply-chain.json", snapshot["supply_chain"])
    write_json(out / "codeowners.json", snapshot["codeowners"])
    write_json(out / "architecture.json", arch)
    (out / "notes.md").write_text(render_notes(snapshot, gaps, sq, impact), encoding="utf-8")

    print(
        "repo-index: "
        f"{snapshot['tracked_files']} files; "
        f"{snapshot['metrics']['graph_nodes']} nodes/{snapshot['metrics']['graph_edges']} edges; "
        f"deps={snapshot['supply_chain']['component_count']}; "
        f"cycles={snapshot['metrics']['dependency_cycles']}; "
        f"boundary_findings={snapshot['metrics']['architecture_boundary_violations']}; "
        f"cache_hits={snapshot['metrics']['semantic_cache_hit_ratio']:.1%}"
    )
    return snapshot


def load_or_build(out: Path, base_ref: str = "origin/main") -> dict[str, Any]:
    current = read_json(out / "index.json")
    if isinstance(current, dict) and int(current.get("schema", 0)) >= 4:
        return current
    return snapshot_command(out, base_ref)


def graph_adjacency(snapshot: dict[str, Any], edge_types: set[str], reverse: bool = False) -> dict[str, list[dict[str, str]]]:
    adjacency: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in snapshot["graph"].get("edges", []):
        if edge.get("type") not in edge_types:
            continue
        source, target = str(edge["from"]), str(edge["to"])
        left, right = (target, source) if reverse else (source, target)
        adjacency[left].append({
            "node": right,
            "type": str(edge["type"]),
            "precision": str(edge.get("precision", "unknown")),
        })
    return adjacency


def traverse(adjacency: dict[str, list[dict[str, str]]], start: str, transitive: bool) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for edge in adjacency.get(current, []):
            node = edge["node"]
            if node in found:
                continue
            found[node] = edge
            if transitive:
                queue.append(node)
    return [found[key] | {"node": key} for key in sorted(found)]


def query_command(out: Path, kind: str, value: str, transitive: bool) -> None:
    snapshot = load_or_build(out)
    if kind == "file":
        row = next((r for r in snapshot["files"] if r["path"] == value), None)
        payload = {
            "file": row,
            "semantic": snapshot.get("semantic", {}).get(value),
            "codeowners": snapshot.get("codeowners", {}).get("file_owners", {}).get(value, []),
            "outgoing": [e for e in snapshot["graph"]["edges"] if e["from"] == f"file:{value}"],
            "incoming": snapshot["graph"]["reverse_edges"].get(f"file:{value}", []),
        }
    elif kind == "symbol":
        needle = value.lower()
        payload = {"symbols": [s for s in snapshot["symbols"] if needle in str(s.get("qualified_name", "")).lower()][:500]}
    elif kind in {"deps", "rdeps"}:
        adjacency = graph_adjacency(snapshot, {"imports", "declares-dependency"}, reverse=(kind == "rdeps"))
        payload = {kind: traverse(adjacency, f"file:{value}", transitive)}
    elif kind == "dependency":
        needle = value.lower()
        payload = {
            "dependencies": [
                n for n in snapshot["supply_chain"]["nodes"]
                if needle in str(n.get("name", "")).lower() or needle in str(n.get("id", "")).lower()
            ][:500]
        }
    elif kind == "subsystem":
        payload = {"files": [r for r in snapshot["files"] if r["subsystem"] == value]}
    elif kind == "owner":
        payload = {
            "files": [
                r for r in snapshot["files"]
                if (r.get("owner") or {}).get("id") == value
                or value in snapshot.get("codeowners", {}).get("file_owners", {}).get(r["path"], [])
            ]
        }
    else:
        raise RuntimeError(f"unsupported query kind: {kind}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def impact_command(out: Path, base_ref: str, paths: list[str]) -> dict[str, Any]:
    snapshot = load_or_build(out, base_ref)
    changed = sorted(set(paths or base.changed_paths(base_ref)))
    payload = semantic._impact_from_paths(snapshot, changed)
    impacted_set = set(payload["affected_files"])
    payload["external_dependencies_touched"] = sorted({
        edge["to"] for edge in snapshot["graph"]["edges"]
        if edge["type"] == "declares-dependency"
        and str(edge["from"]).removeprefix("file:") in impacted_set
    })
    payload["architecture_boundary_findings"] = [
        item for item in snapshot["graph"].get("architecture_boundary_violations", [])
        if item["source"] in impacted_set or item["target"] in impacted_set
    ]
    write_json(out / "impact.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def changed_status(base_ref: str) -> list[dict[str, str]]:
    raw = base.git("diff", "--name-status", "--find-renames", f"{base_ref}...HEAD", check=False)
    rows: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            rows.append({"status": "renamed", "old_path": parts[1], "path": parts[2], "similarity": status[1:]})
        elif len(parts) >= 2:
            label = {"A": "added", "M": "modified", "D": "deleted", "T": "type-changed"}.get(status[:1], status)
            rows.append({"status": label, "path": parts[1]})
    return rows


def diff_command(out: Path, base_ref: str) -> dict[str, Any]:
    snapshot = load_or_build(out, base_ref)
    changes = changed_status(base_ref)
    current_paths = [row["path"] for row in changes if row["status"] != "deleted"]
    impact = semantic._impact_from_paths(snapshot, current_paths)
    affected = set(impact["affected_files"])
    edges = [
        edge for edge in snapshot["graph"]["edges"]
        if str(edge["from"]).removeprefix("file:") in affected
        or str(edge["to"]).removeprefix("file:") in affected
    ]
    payload = {
        "schema": 1,
        "base": base_ref,
        "head": base.git("rev-parse", "HEAD").strip(),
        "changes": changes,
        "impact": impact,
        "current_graph_edges_touching_impact": edges,
        "current_boundary_findings_touching_impact": [
            item for item in snapshot["graph"].get("architecture_boundary_violations", [])
            if item["source"] in affected or item["target"] in affected
        ],
        "note": "This graph diff combines Git path status with the current-head semantic graph. Deleted historical semantic edges require a stored base snapshot and are not inferred as current edges.",
    }
    write_json(out / "graph-diff.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def doctor_command(out: Path) -> int:
    snapshot = load_or_build(out)
    m = snapshot["metrics"]
    issues: list[str] = []
    warnings: list[str] = []
    if m["semantic_parse_failures"]:
        issues.append(f"semantic parse failures={m['semantic_parse_failures']}")
    if m["unowned_files"]:
        warnings.append(f"architecturally unowned files={m['unowned_files']}")
    if m["dependency_cycles"]:
        warnings.append(f"dependency cycles={m['dependency_cycles']}")
    high_boundaries = [v for v in snapshot["graph"].get("architecture_boundary_violations", []) if v.get("severity") == "high"]
    if high_boundaries:
        warnings.append(f"high architecture boundary findings={len(high_boundaries)}")
    if not snapshot["graph"].get("edges"):
        issues.append("graph has no edges")
    if snapshot["supply_chain"]["component_count"] == 0:
        warnings.append("no external dependency components parsed")
    report = {
        "source_digest": snapshot["source_digest"],
        "healthy": not issues,
        "issues": issues,
        "warnings": warnings,
        "metrics": m,
        "largest_cycles": snapshot["graph"].get("dependency_cycles", [])[:10],
        "high_boundary_findings": high_boundaries[:25],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not issues else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="generate canonical repository knowledge graph")
    snap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    snap.add_argument("--base", default="origin/main")

    check = sub.add_parser("check", help="validate all repository-intelligence contracts")
    check.add_argument("--gate", action="store_true")
    check.add_argument("--base", default="origin/main")

    gate = sub.add_parser("gate", help="require augmentation note for build-affecting changes")
    gate.add_argument("--base", default="origin/main")

    impact = sub.add_parser("impact", help="compute transitive reverse change impact")
    impact.add_argument("--out", type=Path, default=DEFAULT_OUT)
    impact.add_argument("--base", default="origin/main")
    impact.add_argument("paths", nargs="*")

    diff = sub.add_parser("diff", help="combine Git change status with current semantic graph impact")
    diff.add_argument("--out", type=Path, default=DEFAULT_OUT)
    diff.add_argument("--base", default="origin/main")

    query = sub.add_parser("query", help="query files, symbols, dependencies, owners and graph edges")
    query.add_argument("--out", type=Path, default=DEFAULT_OUT)
    query.add_argument("--kind", choices=["file", "symbol", "deps", "rdeps", "dependency", "subsystem", "owner"], required=True)
    query.add_argument("--value", required=True)
    query.add_argument("--transitive", action="store_true")

    doctor = sub.add_parser("doctor", help="report index health without treating existing architecture debt as fatal")
    doctor.add_argument("--out", type=Path, default=DEFAULT_OUT)

    dep = sub.add_parser("dependabot-notes", help="render live Dependabot API data into build notes")
    dep.add_argument("--alerts", type=Path)
    dep.add_argument("--prs", type=Path)
    dep.add_argument("--out", type=Path, default=DEFAULT_OUT / "dependabot-notes.md")

    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            snapshot_command(args.out, args.base)
        elif args.command == "check":
            validate_contracts()
            if args.gate:
                base.note_gate(args.base)
        elif args.command == "gate":
            validate_contracts()
            base.note_gate(args.base)
        elif args.command == "impact":
            impact_command(args.out, args.base, args.paths)
        elif args.command == "diff":
            diff_command(args.out, args.base)
        elif args.command == "query":
            query_command(args.out, args.kind, args.value, args.transitive)
        elif args.command == "doctor":
            return doctor_command(args.out)
        elif args.command == "dependabot-notes":
            base.dependabot_notes(args.alerts, args.prs, args.out)
        return 0
    except RuntimeError as exc:
        print(f"repo-index: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
