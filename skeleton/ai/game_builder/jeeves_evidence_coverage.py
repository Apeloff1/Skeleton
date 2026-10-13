"""Per-volume static evidence coverage, never release or model verification.

This surface is bounded by the signed source census and the canonical graph.
A linked test file proves only that the file exists and is declared in the
masterplan; it does not prove the test passed or even that it was run.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_completion_census import JeevesCompletionCensus, _json_object
from .jeeves_evidence_graph import JeevesEvidenceGraph, _safe_path

SCHEMA = "skeleton.ai.jeeves_evidence_coverage.v1"
MAX_PAGE = 80
MAX_VOLUMES = 2000
SOURCE = "machine/ai_master_plan.json"


class JeevesEvidenceCoverage:
    """Proof inventory with explicit evidence gaps and no execution surface."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical inventory required")
        inventory._require_scanned()
        self.inv = inventory

    def _assemble(self, expected_snapshot=None, expected_graph_digest=None):
        inventory = self.inv
        graph = JeevesEvidenceGraph(inventory).overview(
            expected_snapshot=expected_snapshot)
        if (expected_graph_digest is not None and
            expected_graph_digest != graph["digest"]):
            raise JeevesAppwideError("stale coverage graph source identity")
        text = inventory._safe_file(SOURCE, max_size=1_000_000)
        document = _json_object(text, SOURCE)
        volumes = document.get("volumes")
        if type(volumes) is not list or not 1 <= len(volumes) <= MAX_VOLUMES:
            raise JeevesAppwideError("bounded canonical volume list required")
        paths = {}
        dirs = set()
        for entry in inventory._files.values():
            if not entry.readable:
                continue
            pieces = entry.path.split("/")
            for end in range(1, len(pieces)):
                dirs.add("/".join(pieces[:end]))
        facets = (
            ("implementation", "implementation_paths"),
            ("test", "tests"),
            ("evaluation", "evaluations"),
        )
        records = []
        keys = set()
        for volume in volumes:
            if type(volume) is not dict or type(volume.get("key")) is not str:
                raise JeevesAppwideError("invalid canonical volume row")
            identifier = volume["key"]
            if identifier in keys:
                raise JeevesAppwideError("duplicate canonical volume ID")
            keys.add(identifier)
            dimensions = {}
            gap_types = []
            for kind, field in facets:
                refs = volume.get(field, [])
                if type(refs) is not list or any(type(p) is not str for p in refs):
                    raise JeevesAppwideError("invalid typed volume evidence references")
                unique = sorted(set(refs))
                if len(unique) > 1024:
                    raise JeevesAppwideError("unbounded volume evidence reference set")
                available = sum(
                    1 for reference in unique
                    if _safe_path(reference, inventory, dirs) is not None)
                dimensions[kind] = {
                    "declared": len(unique),
                    "present": available,
                    "unavailable_or_restricted": len(unique) - available,
                    "executed_and_passed": None,
                }
                if not unique:
                    gap_types.append("no_declared_" + kind + "_references")
                elif available == 0:
                    gap_types.append("no_present_" + kind + "_references")
                elif len(unique) > available:
                    gap_types.append("incomplete_" + kind + "_reference_coverage")
            records.append({
                "id": identifier,
                "title": str(volume.get("title", identifier))[:160],
                "implementation_maturity": str(volume.get(
                    "implementation_status", "unclassified")),
                "enterprise_maturity": str(volume.get(
                    "enterprise_grade_state", "unclassified")),
                "dimensions": dimensions,
                "static_evidence_gaps": gap_types,
                "static_evidence_paths_complete": not gap_types,
                "runtime_tests_verified": None,
                "enterprise_qualified": False,
                "auto_signature_or_source_mutation": False,
            })
        records.sort(key=lambda v: v["id"])
        gaps = Counter(gap for row in records for gap in row["static_evidence_gaps"])
        maturity = Counter(row["implementation_maturity"] for row in records)
        grade = Counter(row["enterprise_maturity"] for row in records)
        summary = {
            "schema": SCHEMA,
            "inventory_snapshot": inventory._digest,
            "graph_digest": graph["digest"],
            "masterplan_sha256": sha256(text.encode("utf-8")).hexdigest(),
            "total_volumes": len(records),
            "static_facet_complete": sum(v["static_evidence_paths_complete"]
                                         for v in records),
            "static_evidence_gaps": dict(sorted(gaps.items())),
            "implementation_states": dict(sorted(maturity.items())),
            "enterprise_states": dict(sorted(grade.items())),
            "executable_test_pass_count": None,
            "real_app_capability_coverage": None,
            "asserted_release_qualified": False,
            "declared_evidence_is_not_executable_qualification": True,
            "untrusted_implementation_paths_are_never_executed": True,
        }
        return {**summary, "digest": digest(summary)}, records

    def overview(self, *, expected_snapshot=None, expected_graph_digest=None):
        report, _ = self._assemble(expected_snapshot, expected_graph_digest)
        return report

    def page(self, *, offset=0, limit=25, only_gaps=False,
             expected_coverage_digest=None, expected_snapshot=None,
             expected_graph_digest=None):
        if type(offset) is not int or not 0 <= offset <= MAX_VOLUMES:
            raise JeevesAppwideError("bounded coverage offset needed")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded coverage page length required")
        if type(only_gaps) is not bool:
            raise JeevesAppwideError("boolean-only gap filter required")
        summary, rows = self._assemble(expected_snapshot, expected_graph_digest)
        if (expected_coverage_digest is not None and
            expected_coverage_digest != summary["digest"]):
            raise JeevesAppwideError("stale coverage report evidence")
        if only_gaps:
            rows = [row for row in rows if row["static_evidence_gaps"]]
        selected = rows[offset:offset + limit]
        result = {
            "schema": SCHEMA + ".page",
            "overview_digest": summary["digest"],
            "offset": offset, "limit": limit, "only_gaps": only_gaps,
            "total_matches": len(rows),
            "next_offset": offset + len(selected)
                if offset + len(selected) < len(rows) else None,
            "volumes": selected,
            "no_test_or_signature_promotion_performed": True,
            "acceptance_requires_exact_head_independent_evidence": True,
        }
        return {**result, "digest": digest(result)}
