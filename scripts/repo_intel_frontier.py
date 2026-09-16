#!/usr/bin/env python3
"""Frontier Skeleton repository knowledge-graph CLI.

This is the top compositional layer. It preserves the canonical index
(semantic graph + structured supply chain + CODEOWNERS + architecture rules)
and adds runtime/build surfaces, deterministic history hotspots, batch evidence,
workflow/build-target relationships, ranked structural test evidence, compact
agent retrieval, and richer change intelligence. Core indexing remains
network-free and stdlib-only.

The frontier cache is self-validating: every read compares a cheap content-aware
workspace fingerprint and regenerates the snapshot when tracked state changes.
Graph composition also preserves relation metadata so distinct dependency scopes,
requirements, and build relationships cannot collapse into one edge merely because
they share the same endpoints and relation type.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_index as core  # noqa: E402
import repo_intel as base  # noqa: E402
import repo_intel_deep as deep  # noqa: E402
import repo_intel_sota as semantic  # noqa: E402
import repo_intel_test_evidence as test_evidence  # noqa: E402

ROOT = base.ROOT
DEFAULT_OUT = base.DEFAULT_OUT
REQUIRED_SNAPSHOT_OUTPUTS = (
    "index.json",
    "graph.json",
    "symbols.json",
    "build-map.json",
    "impact.json",
    "change-set.json",
    "gaps.json",
    "security-quality.json",
    "metrics.json",
    "supply-chain.json",
    "codeowners.json",
    "architecture.json",
    "dependencies.json",
    "surfaces.json",
    "hotspots.json",
    "history.json",
    "batch-status.json",
    "search-catalog.json",
    "build-relationships.json",
    "test-evidence.json",
    "notes.md",
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def validate_contracts() -> None:
    core.validate_contracts()
    deep.check_contracts()
    test_evidence.check_contracts()
    print("repo-intel-frontier: canonical + deep + test-evidence contracts valid")


def _workspace_fingerprint() -> str:
    """Return a cheap content-aware identity for the tracked index + worktree.

    `git write-tree` gives one compact identity for staged/tracked state. The
    porcelain status captures status/mode changes, while only unstaged changed
    files are content-hashed. Untracked files are intentionally excluded because
    the repository index models tracked source until files are added to Git.
    """
    tree = base.git("write-tree", check=False).strip()
    if not tree:
        tree = base.git("ls-files", "-s", check=False)
    status = base.git("status", "--porcelain=v1", "-z", "-uno", check=False)
    dirty = sorted(filter(None, base.git("diff", "--name-only", "-z", check=False).split("\0")))

    digest = hashlib.sha256()
    digest.update(tree.encode("utf-8", errors="surrogateescape"))
    digest.update(b"\0status\0")
    digest.update(status.encode("utf-8", errors="surrogateescape"))
    for path in dirty:
        digest.update(b"\0path\0")
        digest.update(path.encode("utf-8", errors="surrogateescape"))
        target = ROOT / path
        if target.is_file():
            blob = base.git("hash-object", "--", path, check=False).strip()
            digest.update(blob.encode("ascii", errors="ignore"))
        else:
            digest.update(b"<deleted-or-non-file>")
    return digest.hexdigest()


def _edge_key(edge: dict[str, Any]) -> str:
    """Identity preserving all relation metadata, not only graph endpoints."""
    return json.dumps(edge, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _merge_relationships(snapshot: dict[str, Any], relationships: dict[str, Any]) -> None:
    graph = snapshot["graph"]
    nodes_by_id = {str(node["id"]): node for node in graph.get("nodes", [])}
    for node in relationships.get("nodes", []):
        nodes_by_id[str(node["id"])] = node

    # Exact duplicate edges collapse, but metadata variants remain independent.
    edge_by_key = {_edge_key(edge): edge for edge in graph.get("edges", [])}
    for edge in relationships.get("edges", []):
        edge_by_key[_edge_key(edge)] = edge
    graph["nodes"] = [nodes_by_id[key] for key in sorted(nodes_by_id)]
    graph["edges"] = sorted(
        edge_by_key.values(),
        key=lambda edge: (
            str(edge.get("from", "")),
            str(edge.get("to", "")),
            str(edge.get("type", "")),
            _edge_key(edge),
        ),
    )

    reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph["edges"]:
        incoming: dict[str, Any] = {
            "from": str(edge["from"]),
            "type": str(edge["type"]),
            "precision": str(edge.get("precision", "unknown")),
        }
        for key, value in edge.items():
            if key not in {"from", "to", "type", "precision"}:
                incoming[key] = value
        reverse[str(edge["to"])].append(incoming)
    graph["reverse_edges"] = {
        key: sorted(value, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        for key, value in sorted(reverse.items())
    }


def _relationship_variant_count(edges: list[dict[str, Any]]) -> int:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for edge in edges:
        counts[(str(edge.get("from")), str(edge.get("to")), str(edge.get("type")))] += 1
    return sum(max(0, count - 1) for count in counts.values())


def build_snapshot(out: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build canonical graph then add frontier layers without duplicating package nodes."""
    snapshot = core.build_snapshot(out)
    dependencies = deep.dependency_inventory(snapshot)
    surfaces = deep.surface_inventory(snapshot)
    # Canonical supply-chain nodes already model packages. Frontier relationships
    # add workflow/build targets only to avoid duplicate dependency graph nodes.
    relationships = deep.build_relationships(snapshot, {"packages": []})
    history = deep.history_metrics(snapshot)
    hotspots = deep.hotspot_inventory(snapshot, history, relationships["edges"])
    batches = deep.batch_status(snapshot)
    catalog = deep.search_catalog(snapshot, surfaces, hotspots, dependencies)

    _merge_relationships(snapshot, relationships)
    tests = test_evidence.build(snapshot)
    snapshot["test_evidence"] = tests

    history_by_path = history["files"]
    centrality = deep._centrality(snapshot, [])
    hotspot_by_path = {item["path"]: item for item in hotspots["hotspots"]}
    for row in snapshot["files"]:
        path = row["path"]
        row["history"] = history_by_path.get(path, {})
        row["centrality"] = centrality.get(path, {"fan_in": 0, "fan_out": 0})
        row["hotspot_score"] = hotspot_by_path.get(path, {}).get("score", 0.0)

    snapshot["schema"] = 5
    metrics = snapshot["metrics"]
    metrics.update(
        {
            "graph_nodes": len(snapshot["graph"]["nodes"]),
            "graph_edges": len(snapshot["graph"]["edges"]),
            "relationship_metadata_variants": _relationship_variant_count(snapshot["graph"]["edges"]),
            "declared_dependency_records": dependencies["package_count"],
            "package_script_count": len(dependencies["package_scripts"]),
            "route_count": surfaces["route_count"],
            "environment_variable_count": surfaces["environment_variable_count"],
            "undocumented_environment_variable_count": len(surfaces["undocumented_environment_variables"]),
            "build_target_count": len(relationships["build_targets"]),
            "history_window_commits": history["window_commits_observed"],
            "search_document_count": catalog["document_count"],
            "batch_evidence_noted": sum(
                counts.get("evidence-noted", 0) for counts in batches["lane_counts"].values()
            ),
            "test_evidence_links": tests["evidence_link_count"],
            "source_test_evidence_ratio": tests["source_evidence_ratio"],
        }
    )
    bundle = {
        "dependencies": dependencies,
        "surfaces": surfaces,
        "relationships": relationships,
        "history": history,
        "hotspots": hotspots,
        "batch_status": batches,
        "search_catalog": catalog,
        "test_evidence": tests,
    }
    return snapshot, bundle


def build_map(snapshot: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    mapping = core.build_map(snapshot)
    mapping.update(
        {
            "schema": 5,
            "workspace_fingerprint": snapshot.get("workspace_fingerprint"),
            "declared_dependency_records": bundle["dependencies"]["package_count"],
            "package_scripts": bundle["dependencies"]["package_scripts"],
            "build_targets": bundle["relationships"]["build_targets"],
            "routes": bundle["surfaces"]["routes"],
            "environment_variable_count": bundle["surfaces"]["environment_variable_count"],
            "hotspots": bundle["hotspots"]["hotspots"][:50],
            "batch_lane_counts": bundle["batch_status"]["lane_counts"],
            "test_evidence": {
                "source_evidence_ratio": bundle["test_evidence"]["source_evidence_ratio"],
                "evidence_link_count": bundle["test_evidence"]["evidence_link_count"],
                "test_file_count": bundle["test_evidence"]["test_file_count"],
            },
        }
    )
    return mapping


def impact_payload(snapshot: dict[str, Any], changed: list[str]) -> dict[str, Any]:
    payload = semantic._impact_from_paths(snapshot, changed)
    impacted = set(payload["affected_files"])
    payload["external_dependencies_touched"] = sorted(
        {
            edge["to"]
            for edge in snapshot["graph"]["edges"]
            if edge["type"] == "declares-dependency"
            and str(edge["from"]).removeprefix("file:") in impacted
        }
    )
    payload["architecture_boundary_findings"] = [
        item
        for item in snapshot["graph"].get("architecture_boundary_violations", [])
        if item["source"] in impacted or item["target"] in impacted
    ]
    payload["workflow_files_touched"] = sorted(
        path for path in impacted if path.startswith(".github/workflows/")
    )
    ranked = test_evidence.select_for_impact(payload, snapshot.get("test_evidence", {}), limit=100)
    payload["ranked_candidate_tests"] = ranked
    payload["ranked_candidate_test_count"] = len(ranked)
    payload["test_selection_semantics"] = (
        "Ranked tests are structural relevance evidence only; required integration/release gates remain authoritative."
    )
    return payload


def render_notes(
    snapshot: dict[str, Any],
    bundle: dict[str, Any],
    gaps: dict[str, Any],
    sq: dict[str, Any],
    impact: dict[str, Any],
) -> str:
    text = core.render_notes(snapshot, gaps, sq, impact).rstrip()
    m = snapshot["metrics"]
    hot = bundle["hotspots"]["hotspots"][:8]
    top_tests = impact.get("ranked_candidate_tests", [])[:8]
    lines = [
        text,
        "",
        "## Frontier build/runtime intelligence",
        "",
        f"- Direct dependency declarations: **{m['declared_dependency_records']}**; canonical external components: "
        f"**{m.get('external_dependency_components', 0)}**.",
        f"- Package-manager build scripts: **{m['package_script_count']}**; Make targets: **{m['build_target_count']}**.",
        f"- Runtime/creator routes indexed: **{m['route_count']}**.",
        f"- Environment-variable names referenced: **{m['environment_variable_count']}**; "
        f"**{m['undocumented_environment_variable_count']}** absent from tracked `.env.example` files.",
        f"- Preserved relationship metadata variants: **{m['relationship_metadata_variants']}**.",
        f"- Structural test-evidence links: **{m['test_evidence_links']}**; source files with ranked test evidence: "
        f"**{m['source_test_evidence_ratio']:.1%}**.",
        f"- Deterministic churn window: **{m['history_window_commits']} commits** relative to HEAD time.",
        f"- Agent retrieval documents: **{m['search_document_count']}**.",
        f"- Batch evidence notes: **{m['batch_evidence_noted']}/100** batches referenced. "
        "Reference does not imply completion.",
        "- Snapshot reads are self-validating against a content-aware tracked-workspace fingerprint; stale caches rebuild automatically.",
        "",
        "### Highest-attention hotspots",
        "",
    ]
    for item in hot:
        lines.append(
            f"- `{item['path']}` — score **{item['score']}**, touches={item['touches']}, "
            f"fan-in={item['fan_in']}, fan-out={item['fan_out']}, risk={item['risk']}."
        )
    if not hot:
        lines.append("- No hotspot records generated.")
    lines.extend(["", "### Focused test evidence for current impact", ""])
    for item in top_tests:
        lines.append(
            f"- `{item['test']}` — confidence **{item['confidence']:.3f}**; "
            f"reasons={', '.join(item['reasons'][:3])}."
        )
    if not top_tests:
        lines.append("- No ranked structural test evidence for the current impact set.")
    lines.extend(
        [
            "",
            "Hotspot scores are relative engineering-attention signals, not quality/security grades. "
            "Test confidence is structural relevance, not coverage or sufficiency. Dependency declarations are offline "
            "inventory; GitHub Dependency Graph and Dependabot remain authoritative for resolved/transitive vulnerability state.",
            "",
        ]
    )
    return "\n".join(lines)


def snapshot_command(out: Path, base_ref: str) -> dict[str, Any]:
    validate_contracts()
    out.mkdir(parents=True, exist_ok=True)
    start_fingerprint = _workspace_fingerprint()
    snapshot, bundle = build_snapshot(out)
    gaps = base.feature_gaps(snapshot)
    sq = base.security_quality(snapshot)
    changed = base.changed_paths(base_ref)
    impact = impact_payload(snapshot, changed)
    change_set = deep.change_set(base_ref, impact)
    arch = core.architecture_report(snapshot)
    end_fingerprint = _workspace_fingerprint()
    if end_fingerprint != start_fingerprint:
        raise RuntimeError(
            "tracked workspace changed while the repository index was being built; rerun to avoid publishing a mixed snapshot"
        )
    snapshot["workspace_fingerprint"] = end_fingerprint
    snapshot["metrics"]["workspace_fingerprint_verified"] = True
    mapping = build_map(snapshot, bundle)

    write_json(out / "index.json", snapshot)
    write_json(out / "graph.json", snapshot["graph"])
    write_json(out / "symbols.json", {"schema": 2, "symbols": snapshot["symbols"]})
    write_json(out / "build-map.json", mapping)
    write_json(out / "impact.json", impact)
    write_json(out / "change-set.json", change_set)
    write_json(out / "gaps.json", gaps)
    write_json(out / "security-quality.json", sq)
    write_json(out / "metrics.json", snapshot["metrics"])
    write_json(out / "supply-chain.json", snapshot["supply_chain"])
    write_json(out / "codeowners.json", snapshot["codeowners"])
    write_json(out / "architecture.json", arch)
    write_json(out / "dependencies.json", bundle["dependencies"])
    write_json(out / "surfaces.json", bundle["surfaces"])
    write_json(out / "hotspots.json", bundle["hotspots"])
    write_json(out / "history.json", bundle["history"])
    write_json(out / "batch-status.json", bundle["batch_status"])
    write_json(out / "search-catalog.json", bundle["search_catalog"])
    write_json(out / "build-relationships.json", bundle["relationships"])
    write_json(out / "test-evidence.json", bundle["test_evidence"])
    (out / "notes.md").write_text(render_notes(snapshot, bundle, gaps, sq, impact), encoding="utf-8")

    print(
        "repo-intel-frontier: "
        f"{snapshot['tracked_files']} files; {snapshot['metrics']['graph_nodes']} nodes/"
        f"{snapshot['metrics']['graph_edges']} edges; deps={snapshot['supply_chain']['component_count']}; "
        f"routes={snapshot['metrics']['route_count']}; targets={snapshot['metrics']['build_target_count']}; "
        f"test_evidence={snapshot['metrics']['test_evidence_links']}; "
        f"cache_hits={snapshot['metrics']['semantic_cache_hit_ratio']:.1%}"
    )
    return snapshot


def _snapshot_is_fresh(current: Any, out: Path) -> bool:
    if not isinstance(current, dict) or int(current.get("schema", 0)) < 5:
        return False
    if any(not (out / name).exists() for name in REQUIRED_SNAPSHOT_OUTPUTS):
        return False
    fingerprint = current.get("workspace_fingerprint")
    return isinstance(fingerprint, str) and fingerprint == _workspace_fingerprint()


def load_or_build(out: Path, base_ref: str = "origin/main") -> dict[str, Any]:
    current = read_json(out / "index.json")
    if _snapshot_is_fresh(current, out):
        return current
    return snapshot_command(out, base_ref)


def query_command(out: Path, kind: str, value: str, transitive: bool, limit: int) -> None:
    snapshot = load_or_build(out)
    needle = value.lower()
    if kind == "file":
        row = next((item for item in snapshot["files"] if item["path"] == value), None)
        payload = {
            "file": row,
            "semantic": snapshot.get("semantic", {}).get(value),
            "codeowners": snapshot.get("codeowners", {}).get("file_owners", {}).get(value, []),
            "outgoing": [edge for edge in snapshot["graph"]["edges"] if edge["from"] == f"file:{value}"],
            "incoming": snapshot["graph"]["reverse_edges"].get(f"file:{value}", []),
            "ranked_tests": snapshot.get("test_evidence", {}).get("by_source", {}).get(value, []),
        }
    elif kind == "symbol":
        payload = {
            "symbols": [
                symbol
                for symbol in snapshot["symbols"]
                if needle in str(symbol.get("qualified_name", "")).lower()
            ][:limit]
        }
    elif kind in {"deps", "rdeps"}:
        adjacency = core.graph_adjacency(
            snapshot,
            {"imports", "declares-dependency", "workflow-uses", "build-uses"},
            reverse=(kind == "rdeps"),
        )
        payload = {kind: core.traverse(adjacency, f"file:{value}", transitive)[:limit]}
    elif kind == "dependency":
        payload = {
            "dependencies": [
                node
                for node in snapshot["supply_chain"]["nodes"]
                if needle in str(node.get("name", "")).lower()
                or needle in str(node.get("id", "")).lower()
            ][:limit]
        }
    elif kind == "subsystem":
        payload = {"files": [row for row in snapshot["files"] if row["subsystem"] == value][:limit]}
    elif kind == "owner":
        payload = {
            "files": [
                row
                for row in snapshot["files"]
                if (row.get("owner") or {}).get("id") == value
                or value in snapshot.get("codeowners", {}).get("file_owners", {}).get(row["path"], [])
            ][:limit]
        }
    elif kind == "route":
        surfaces = read_json(out / "surfaces.json", {"routes": []})
        payload = {
            "routes": [
                item
                for item in surfaces.get("routes", [])
                if needle in str(item.get("route", "")).lower()
                or needle in str(item.get("path", "")).lower()
            ][:limit]
        }
    elif kind == "env":
        surfaces = read_json(out / "surfaces.json", {"environment_variables": []})
        payload = {
            "environment_variables": [
                item
                for item in surfaces.get("environment_variables", [])
                if needle in str(item.get("name", "")).lower()
            ][:limit]
        }
    elif kind == "hotspot":
        hotspots = read_json(out / "hotspots.json", {"hotspots": []}).get("hotspots", [])
        payload = {"hotspots": [item for item in hotspots if not value or needle in item["path"].lower()][:limit]}
    elif kind == "batch":
        batches = read_json(out / "batch-status.json", {"batches": []}).get("batches", [])
        payload = {
            "batches": [
                item
                for item in batches
                if needle in str(item.get("id", "")).lower()
                or needle in str(item.get("lane", "")).lower()
                or needle in str(item.get("title", "")).lower()
            ][:limit]
        }
    elif kind == "tests":
        evidence = read_json(out / "test-evidence.json", {"by_source": {}})
        by_source = evidence.get("by_source", {})
        if value in by_source:
            payload = {"source": value, "ranked_tests": by_source[value][:limit]}
        else:
            payload = {
                "sources": [
                    {"source": source, "ranked_tests": items[:limit]}
                    for source, items in by_source.items()
                    if needle in source.lower()
                ][:limit]
            }
    elif kind == "search":
        catalog = read_json(out / "search-catalog.json", {"documents": []})
        payload = {"results": deep.search(catalog, value, limit=limit)}
    else:
        raise RuntimeError(f"unsupported query kind: {kind}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def impact_command(out: Path, base_ref: str, paths: list[str]) -> dict[str, Any]:
    snapshot = load_or_build(out, base_ref)
    changed = sorted(set(paths or base.changed_paths(base_ref)))
    payload = impact_payload(snapshot, changed)
    write_json(out / "impact.json", payload)
    write_json(out / "change-set.json", deep.change_set(base_ref, payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def diff_command(out: Path, base_ref: str) -> dict[str, Any]:
    # Canonical diff logic operates correctly on schema-5 snapshots and benefits
    # from the extra workflow/build edges already present in the graph.
    load_or_build(out, base_ref)
    return core.diff_command(out, base_ref)


def doctor_command(out: Path) -> int:
    snapshot = load_or_build(out)
    m = snapshot["metrics"]
    blockers: list[str] = []
    advisories: list[str] = []
    if m.get("semantic_parse_failures"):
        blockers.append(f"semantic parse failures={m['semantic_parse_failures']}")
    if not snapshot["graph"].get("edges"):
        blockers.append("graph has no edges")
    if not m.get("workspace_fingerprint_verified"):
        blockers.append("workspace fingerprint was not verified during snapshot construction")
    if m.get("unowned_files"):
        advisories.append(f"architecturally unowned files={m['unowned_files']}")
    if m.get("dependency_cycles"):
        advisories.append(f"dependency cycles={m['dependency_cycles']}")
    if m.get("architecture_boundary_violations"):
        advisories.append(f"architecture boundary findings={m['architecture_boundary_violations']}")
    if m.get("undocumented_environment_variable_count"):
        advisories.append(
            f"environment variables absent from tracked examples={m['undocumented_environment_variable_count']}"
        )
    report = {
        "schema": 3,
        "source_digest": snapshot["source_digest"],
        "workspace_fingerprint": snapshot.get("workspace_fingerprint"),
        "healthy": not blockers,
        "blockers": blockers,
        "advisories": advisories,
        "metrics": m,
        "top_hotspots": read_json(out / "hotspots.json", {"hotspots": []}).get("hotspots", [])[:20],
        "largest_cycles": snapshot["graph"].get("dependency_cycles", [])[:10],
        "test_evidence": {
            "source_evidence_ratio": m.get("source_test_evidence_ratio", 0.0),
            "evidence_links": m.get("test_evidence_links", 0),
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not blockers else 1


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
    diff = sub.add_parser("diff")
    diff.add_argument("--out", type=Path, default=DEFAULT_OUT)
    diff.add_argument("--base", default="origin/main")
    query = sub.add_parser("query")
    query.add_argument("--out", type=Path, default=DEFAULT_OUT)
    query.add_argument(
        "--kind",
        choices=[
            "file",
            "symbol",
            "deps",
            "rdeps",
            "dependency",
            "subsystem",
            "owner",
            "route",
            "env",
            "hotspot",
            "batch",
            "tests",
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
