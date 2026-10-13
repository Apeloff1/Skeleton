"""Source-linked candidate validation plan; never executes tests or signs gates.

Given exact checked-out source paths, traces the canonical graph to declared
masterplan tests and evaluation workflow files. Missing/cross-scope references
become visible gaps. This is *not* a complete dynamic dependency/call graph,
nor a replacement for the repo's mandatory release gate policy.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, PRIVATE, _relative, digest
from .jeeves_evidence_graph import JeevesEvidenceGraph

SCHEMA = "skeleton.ai.jeeves_change_validation_frontier.v1"
MAX_PATHS = 32
MAX_ITEMS = 1000
MAX_PAGE = 80


class JeevesChangeValidationFrontier:
    """Read-only source→volume→declared test/workflow planner."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical scanned source inventory required")
        inventory._require_scanned()
        self.inv = inventory

    def _build(self, paths, *, expected_snapshot=None, expected_graph_digest=None):
        if type(paths) is not list or not 1 <= len(paths) <= MAX_PATHS:
            raise JeevesAppwideError("one to 32 changed source paths required")
        selected = []
        for candidate in paths:
            path = _relative(candidate)
            if path in selected:
                raise JeevesAppwideError("duplicate changed source path")
            entry = self.inv._files.get(path)
            if entry is None or not entry.readable or PRIVATE.search(path):
                raise JeevesAppwideError("unknown or restricted source cannot be scoped")
            selected.append(path)
        nodes, edges, overview = JeevesEvidenceGraph(self.inv)._build(
            expected_snapshot=expected_snapshot)
        if (expected_graph_digest is not None and
            expected_graph_digest != overview["digest"]):
            raise JeevesAppwideError("stale graph; cannot plan validation")
        source_recs = []
        volume_hits = defaultdict(set)
        declared = defaultdict(set)
        # Map volume source implementation paths and required-file declarations.
        for edge in edges.values():
            if edge["from"].startswith("vol:") and edge[
                "relation"] in ("declares_implementation_at", "declares_test_at",
                                "declares_evaluation_at"):
                declared[edge["from"]].add((edge["relation"], edge["to"]))
        for path in sorted(selected):
            content_sha = None
            entry = self.inv._files[path]
            if entry.kind in ("source", "text") and entry.bytes <= 256_000:
                text = self.inv._safe_file(path)
                content_sha = sha256(text.encode()).hexdigest()
            source_recs.append({
                "path": path, "sha256": content_sha,
                "source_content_verified": content_sha is not None,
                "inventory_recorded_bytes": entry.bytes,
            })
            ids = ["path:" + path]
            parts = path.split("/")
            ids += ["path:" + "/".join(parts[:i])
                    for i in range(1, len(parts))]
            for volume, links in declared.items():
                if any(relation == "declares_implementation_at" and source in ids
                       for relation, source in links):
                    volume_hits[volume].add(path)
                elif any(source == "path:" + path for _, source in links):
                    volume_hits[volume].add(path)
        suggested = {}
        incomplete = []
        for volume in sorted(volume_hits):
            links = declared[volume]
            testing = sorted(path[5:] for relation, path in links
                             if relation == "declares_test_at")
            evaluating = sorted(path[5:] for relation, path in links
                                if relation == "declares_evaluation_at")
            if not testing:
                incomplete.append({"volume": volume,
                                   "gap": "no_accessible_declared_test"})
            if not evaluating:
                incomplete.append({"volume": volume,
                                   "gap": "no_accessible_declared_evaluation"})
            for kind, names in (("test", testing), ("evaluation", evaluating)):
                for target in names:
                    key = (kind, target)
                    if key not in suggested:
                        suggested[key] = {
                            "type": kind,
                            "path": target,
                            "declared_by_volumes": [],
                            "source_present": True,
                            "source_executed": False,
                            "exact_head_ci_verified": False,
                            "automatic_test_execution_authorized": False,
                        }
                    suggested[key]["declared_by_volumes"].append(volume)
                    if len(suggested) > MAX_ITEMS:
                        raise JeevesAppwideError("change impact test matrix exceeds cap")
        rows = [suggested[key] for key in sorted(suggested)]
        unknown = sorted(set(selected) - {
            path for hit in volume_hits.values() for path in hit})
        body = {
            "schema": SCHEMA,
            "graph_digest": overview["digest"],
            "inventory_snapshot": self.inv._digest,
            "changed_sources": source_recs,
            "impacted_declared_volumes": len(volume_hits),
            "volume_impacts": [
                {"id": key, "source_paths": sorted(hit),
                 "runtime_impact_verified": False}
                for key, hit in sorted(volume_hits.items())
            ],
            "candidate_validation_items": len(rows),
            "missing_static_test_or_evaluation_refs": incomplete,
            "unmapped_changed_paths": unknown,
            "unknown_impact_is_not_safety": True,
            "mandatory_release_checks_must_still_run": True,
            "all_tests_unexecuted": True,
            "release_qualified": False,
            "source_revisions_proposed_or_written": 0,
        }
        return {**body, "digest": digest(body)}, rows

    def overview(self, *, paths, expected_snapshot=None, expected_graph_digest=None):
        body, _ = self._build(paths, expected_snapshot=expected_snapshot,
                              expected_graph_digest=expected_graph_digest)
        return body

    def page(self, *, paths, offset=0, limit=30, expected_frontier_digest=None,
             expected_snapshot=None, expected_graph_digest=None):
        if type(offset) is not int or not 0 <= offset <= MAX_ITEMS:
            raise JeevesAppwideError("bounded non-negative validation page needed")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded validation evidence page required")
        body, records = self._build(
            paths, expected_snapshot=expected_snapshot,
            expected_graph_digest=expected_graph_digest)
        if (expected_frontier_digest is not None and
            expected_frontier_digest != body["digest"]):
            raise JeevesAppwideError("stale source validation evidence")
        selected = records[offset:offset+limit]
        out = {
            "schema": SCHEMA + ".page",
            "frontier_digest": body["digest"],
            "offset": offset, "limit": limit,
            "total_items": len(records),
            "next_offset": offset+len(selected)
                if offset+len(selected) < len(records) else None,
            "validation_candidates": selected,
            "user_approval_and_ci_authority_not_inferred": True,
        }
        return {**out, "digest": digest(out)}
