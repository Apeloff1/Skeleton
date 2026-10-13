"""Read-only, source-pinned graph joining canonical Jeeves/AI app authorities.

Graph edges mean declared ownership, dependency, scope or file presence.
They never imply executed behavior, tool permission, installed app readiness,
release qualification or a functioning trained model.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from hashlib import sha256
from typing import Any

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, PRIVATE, _relative, digest,
)
from .jeeves_completion_census import JeevesCompletionCensus, _json_object

SCHEMA = "skeleton.ai.jeeves_evidence_graph.v1"
MAX_GRAPH_NODES = 30000
MAX_GRAPH_EDGES = 120000
MAX_LINKS_PER_VOLUME = 128
MAX_PAGE = 80
MAX_DEPTH = 3
MAX_INPUT = 128
CANONICAL_SOURCES = (
    "machine/ai_master_plan.json",
    "machine/ai_capabilities.json",
    "machine/ai_app_construction.json",
    "machine/enterprise_system_architecture.json",
    "machine/enterprise_ai_superiority.json",
    "skeleton/app/manifest.json",
)


def _strict_ref(value: Any) -> str:
    if type(value) is not str or not 1 <= len(value) <= MAX_INPUT or any(
        x in value for x in ("\x00", "\r", "\n", "\\")
    ):
        raise JeevesAppwideError("bounded graph reference required")
    return value


def _safe_path(value: Any, inventory: AppwideInventory, directories: set[str]) -> str | None:
    if type(value) is not str or len(value) > 360:
        return None
    try:
        path = _relative(value)
    except JeevesAppwideError:
        return None
    if PRIVATE.search(path):
        return None
    entry = inventory._files.get(path)
    if entry is not None:
        return path if entry.readable else None
    if path in directories:
        return path
    return None


class JeevesEvidenceGraph:
    """Deterministic graph of canonical declared feature obligations."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("AppwideInventory required for graph")
        inventory._require_scanned()
        self.inv = inventory

    def _build(self, expected_snapshot=None):
        inv = self.inv
        if expected_snapshot is not None and expected_snapshot != inv._digest:
            raise JeevesAppwideError("stale inventory graph snapshot")
        # The census already enforces all eight machine authorities, but its
        # source-only completion score cannot substitute for graph acceptance.
        census = JeevesCompletionCensus(inv).report(expected_snapshot=expected_snapshot)
        data = {}
        for path in CANONICAL_SOURCES:
            data[path] = _json_object(inv._safe_file(path, max_size=1_000_000), path)
        # Build one indexed directory set. A 58k-file inventory cannot
        # afford O(files) prefix traversal for each of many volume paths.
        directories = set()
        for item in inv._files.values():
            if not item.readable:
                continue
            chunks = item.path.split("/")
            for depth in range(1, len(chunks)):
                directories.add("/".join(chunks[:depth]))
        nodes = {}
        edges = {}
        skips = Counter()

        def node(node_id, *, kind, title, maturity="declared", **extra):
            if type(node_id) is not str or not node_id or len(node_id) > 512:
                raise JeevesAppwideError("invalid canonical graph node ID")
            if node_id in nodes:
                if nodes[node_id] != {
                    "id": node_id, "kind": kind, "title": title,
                    "maturity": maturity, **extra,
                }:
                    raise JeevesAppwideError("incompatible duplicate graph node")
                return
            if len(nodes) >= MAX_GRAPH_NODES:
                raise JeevesAppwideError("source graph node budget exceeded")
            nodes[node_id] = {
                "id": node_id, "kind": kind, "title": title,
                "maturity": maturity, **extra,
            }

        def edge(from_id, to_id, relation):
            if from_id not in nodes or to_id not in nodes:
                raise JeevesAppwideError("graph references undefined endpoint")
            key = (from_id, relation, to_id)
            if key in edges:
                return
            if len(edges) >= MAX_GRAPH_EDGES:
                raise JeevesAppwideError("source graph edge budget exceeded")
            edges[key] = {
                "from": from_id, "to": to_id, "relation": relation,
                "evidence_kind": "declared_contract_only",
                "runtime_verified": False,
            }

        def source_link(parent_id, path, relation):
            valid = _safe_path(path, inv, directories)
            if valid is None:
                skips["unavailable_or_restricted_path"] += 1
                return
            dest = "path:" + valid
            node(dest, kind="source_path", title=valid,
                 maturity="file_present_not_executed")
            edge(parent_id, dest, relation)

        master = data["machine/ai_master_plan.json"]
        for volume in master.get("volumes", []):
            if type(volume) is not dict or type(volume.get("key")) is not str:
                raise JeevesAppwideError("invalid volume authority")
            key = _strict_ref(volume["key"])
            src = "vol:" + key
            node(src, kind="masterplan_volume", title=str(volume.get("title", key))[:200],
                 maturity=str(volume.get("implementation_status", "unknown")),
                 enterprise_grade=str(volume.get("enterprise_grade_state", "unknown")))
            paths = volume.get("implementation_paths", [])
            if type(paths) is not list:
                raise JeevesAppwideError("invalid volume implementation paths")
            for path in paths[:MAX_LINKS_PER_VOLUME]:
                source_link(src, path, "declares_implementation_at")
            if len(paths) > MAX_LINKS_PER_VOLUME:
                skips["volume_paths_elided"] += len(paths) - MAX_LINKS_PER_VOLUME
            tests = volume.get("tests", [])
            if type(tests) is not list:
                raise JeevesAppwideError("invalid volume test registry")
            for path in tests[:MAX_LINKS_PER_VOLUME]:
                source_link(src, path, "declares_test_at")
            if len(tests) > MAX_LINKS_PER_VOLUME:
                skips["volume_tests_elided"] += len(tests) - MAX_LINKS_PER_VOLUME
            evals = volume.get("evaluations", [])
            if type(evals) is not list:
                raise JeevesAppwideError("invalid volume evaluation registry")
            for path in evals[:MAX_LINKS_PER_VOLUME]:
                source_link(src, path, "declares_evaluation_at")
            if len(evals) > MAX_LINKS_PER_VOLUME:
                skips["volume_evaluations_elided"] += len(evals) - MAX_LINKS_PER_VOLUME

        app = data["skeleton/app/manifest.json"]
        for service in app.get("services", []):
            identifier = "service:" + _strict_ref(service["name"])
            node(identifier, kind="application_service", title=service["name"],
                 maturity="declared_not_runtime_verified",
                 role=str(service.get("role", "unspecified")))
            source_link(identifier, service.get("path"), "declares_owner_path")
        for path in app.get("required_paths", []):
            valid = _safe_path(path, inv, directories)
            if valid is None:
                skips["app_required_path_missing_or_restricted"] += 1
                continue
            node("required:" + valid, kind="required_app_file", title=valid,
                 maturity="present_not_functional")
            source_link("required:" + valid, valid, "requires_present_path")

        construction = data["machine/ai_app_construction.json"]
        for plane in construction.get("planes", []):
            identifier = "plane:" + _strict_ref(plane["id"])
            node(identifier, kind="architecture_plane", title=plane["id"],
                 maturity="declared_not_operationally_verified")
            source_link(identifier, plane.get("owner"), "declares_owner_path")
        for gap in construction.get("gap_register", []):
            identifier = "gap:" + _strict_ref(gap["id"])
            node(identifier, kind="construction_gap", title=gap["id"],
                 maturity=str(gap.get("status", "unknown")),
                 priority=str(gap.get("priority", "unknown")))

        for capability in data["machine/ai_capabilities.json"].get("capabilities", []):
            identifier = "cap:" + _strict_ref(capability["capability_id"])
            node(identifier, kind="ai_product_capability",
                 title=capability["capability_id"],
                 maturity=str(capability.get("implementation_state", "unknown")),
                 enabled=capability.get("enabled") is True)
            owning = capability.get("owner_plane")
            if type(owning) is str and "plane:" + owning in nodes:
                edge(identifier, "plane:" + owning, "owned_by_plane")
            else:
                skips["capability_without_known_owner"] += 1
            for ref in capability.get("required_planes", []):
                if type(ref) is str and "plane:" + ref in nodes:
                    edge(identifier, "plane:" + ref, "requires_plane")
                else:
                    skips["capability_required_plane_not_found"] += 1

        ent = data["machine/enterprise_system_architecture.json"]
        for domain in ent.get("enterprise_domains", []):
            identifier = "domain:" + _strict_ref(domain["id"])
            node(identifier, kind="enterprise_domain", title=domain["id"])
            for plane_id in domain.get("planes", []):
                if type(plane_id) is str and "plane:" + plane_id in nodes:
                    edge(identifier, "plane:" + plane_id, "covers_plane")
                else:
                    skips["enterprise_domain_undeclared_plane"] += 1
        for work in ent.get("implementation_workstreams", []):
            identifier = "work:" + _strict_ref(work["id"])
            node(identifier, kind="enterprise_workstream",
                 title=str(work.get("name", work["id"]))[:200],
                 priority=str(work.get("priority", "unranked")))
        for work in ent.get("implementation_workstreams", []):
            identifier = "work:" + work["id"]
            for predecessor in work.get("depends_on", []):
                if type(predecessor) is str and "work:" + predecessor in nodes:
                    edge(identifier, "work:" + predecessor, "depends_on")
                else:
                    skips["enterprise_workstream_missing_dependency"] += 1
        for index, journey in enumerate(ent.get("required_journeys", []), 1):
            label = _strict_ref(str(journey)[:MAX_INPUT])
            node("journey:%02d" % index, kind="required_end_to_end_journey",
                 title=label, maturity="required_not_verified")

        superiority = data["machine/enterprise_ai_superiority.json"]
        for journey in superiority.get("end_to_end_qualification", {}).get(
            "golden_journeys", []
        ):
            key = _strict_ref(journey["id"])
            node("ai_journey:" + key, kind="enterprise_ai_journey",
                 title=str(journey.get("name", key))[:200],
                 maturity="required_not_verified")
            for volume_key in journey.get("volume_refs", []):
                vid = "vol:" + str(volume_key)
                if vid in nodes:
                    edge("ai_journey:" + key, vid, "requires_volume_evidence")
                else:
                    skips["unrecognized_journey_volume"] += 1

        # Stable graph digest includes source receipts; metadata-only inventory
        # snapshot is not a claim that all file bytes have been content hashed.
        node_list = [nodes[k] for k in sorted(nodes)]
        edge_list = [edges[k] for k in sorted(edges)]
        receipt = {
            "schema": SCHEMA, "census_digest": census["digest"],
            "inventory_snapshot": inv._digest,
            "source_receipts": {p: census["source_receipts"][p]["sha256"]
                                for p in CANONICAL_SOURCES},
            "node_count": len(node_list), "edge_count": len(edge_list),
            "kind_counts": dict(sorted(Counter(n["kind"] for n in node_list).items())),
            "relation_counts": dict(sorted(Counter(e["relation"] for e in edge_list).items())),
            "skipped_or_unverified": dict(sorted(skips.items())),
            "graph_is_complete": not bool(skips),
            "declarations_are_not_permissions": True,
            "source_presence_is_not_a_running_app": True,
            "all_links_require_independent_acceptance": True,
        }
        return nodes, edges, {**receipt, "digest": digest(receipt)}

    def overview(self, *, expected_snapshot=None):
        _, _, report = self._build(expected_snapshot)
        return report

    def neighborhood(self, node, *, depth=1, limit=30, expected_snapshot=None,
                     expected_graph_digest=None, direction="both"):
        node = _strict_ref(node)
        if type(depth) is not int or not 0 <= depth <= MAX_DEPTH:
            raise JeevesAppwideError("bounded non-negative graph depth required")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded graph page size required")
        if direction not in ("both", "outgoing", "incoming"):
            raise JeevesAppwideError("invalid graph traversal direction")
        nodes, edges, overview = self._build(expected_snapshot)
        if expected_graph_digest is not None and expected_graph_digest != overview["digest"]:
            raise JeevesAppwideError("stale graph identity; re-scan required")
        if node not in nodes:
            raise JeevesAppwideError("unknown or restricted graph node")
        outgoing = defaultdict(list)
        incoming = defaultdict(list)
        for key in edges:
            source, relation, target = key
            outgoing[source].append((target, key))
            incoming[target].append((source, key))
        seen = {node}
        selected = set()
        todo = deque([(node, 0)])
        while todo and len(seen) < limit:
            current, step = todo.popleft()
            if step >= depth:
                continue
            linked = []
            if direction in ("both", "outgoing"):
                linked.extend(outgoing[current])
            if direction in ("both", "incoming"):
                linked.extend(incoming[current])
            for next_id, edge_key in sorted(linked, key=lambda x: (x[0], x[1])):
                if next_id not in seen and len(seen) >= limit:
                    break
                selected.add(edge_key)
                if next_id not in seen:
                    seen.add(next_id)
                    todo.append((next_id, step + 1))
        result = {
            "schema": SCHEMA + ".neighborhood",
            "graph_digest": overview["digest"],
            "root": node, "direction": direction,
            "requested_depth": depth, "node_limit": limit,
            "nodes": [nodes[k] for k in sorted(seen)],
            "edges": [edges[k] for k in sorted(selected)],
            "truncated_by_limit": len(seen) >= limit and bool(todo),
            "query_does_not_confer_execution_authority": True,
            "runtime_verification_performed": False,
        }
        return {**result, "digest": digest(result)}

    def impact(self, paths, *, expected_snapshot=None,
               expected_graph_digest=None, max_results=80):
        """Reverse source-to-volume-to-enterprise evidence impact.

        This is deliberately *declared impact*, not a complete call graph or a
        proof that the targeted codepath is executed by the runtime. Scope is
        bounded before any potentially expensive graph traversal.
        """
        if type(paths) is not list or not 1 <= len(paths) <= 32 or any(
            type(path) is not str for path in paths
        ):
            raise JeevesAppwideError("bounded list of impact source paths required")
        if type(max_results) is not int or not 1 <= max_results <= 200:
            raise JeevesAppwideError("bounded impact evidence page required")
        nodes, edges, overview = self._build(expected_snapshot)
        if expected_graph_digest is not None and (
            expected_graph_digest != overview["digest"]
        ):
            raise JeevesAppwideError("stale source-to-volume impact graph")
        normalized = []
        for source in paths:
            try:
                path = _relative(source)
            except JeevesAppwideError as exc:
                raise JeevesAppwideError("invalid impact target") from exc
            if PRIVATE.search(path) or "path:" + path not in nodes:
                raise JeevesAppwideError("impact target not visible in graph")
            if path in normalized:
                raise JeevesAppwideError("duplicate impact source rejected")
            normalized.append(path)

        dependents = defaultdict(list)
        downstream_volumes = defaultdict(list)
        source_edges = []
        for edge in edges.values():
            if edge["to"].startswith("path:"):
                dependents[edge["to"]].append((edge["from"], edge["relation"]))
            if edge["relation"] == "requires_volume_evidence":
                downstream_volumes[edge["to"]].append(edge["from"])
        hit_map = {}
        for source in sorted(normalized):
            path_id = "path:" + source
            related = []
            for child_id, relation in sorted(dependents[path_id]):
                if child_id.startswith("vol:"):
                    related.extend((node, "enterprise_ai_journey")
                                   for node in downstream_volumes[child_id])
                related.append((child_id, nodes[child_id]["kind"]))
            targets = sorted(set(related))
            hit_map[source] = {
                "path": source,
                "direct_relations": sorted(set(relation for _, relation in
                                               dependents[path_id])),
                "dependent_count": len(targets),
                "dependent_nodes": [
                    {"id": key, "kind": kind, "maturity": nodes[key]["maturity"]}
                    for key, kind in targets[:max_results]
                ],
                "truncated": len(targets) > max_results,
                "source_content_not_loaded": True,
            }
        report = {
            "schema": SCHEMA + ".impact",
            "graph_digest": overview["digest"],
            "inventory_snapshot": overview["inventory_snapshot"],
            "sources": [hit_map[k] for k in sorted(hit_map)],
            "targeted_paths": len(normalized),
            "max_dependents_per_source": max_results,
            "whole_repo_dependency_graph_not_claimed": True,
            "no_changes_or_tests_run": True,
            "declared_impact_is_not_execution_authority": True,
        }
        return {**report, "digest": digest(report)}
