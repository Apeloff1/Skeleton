"""Evidence-honest percent-to-verification for the canonical Skeleton AI app.

A repository metadata status of "verified" is implementation paperwork, NOT
an independent release, runtime, enterprise, quality or trained-model proof.
Scores deliberately separate those denominators and never average them into
a fabricated whole-product percentage. This adapter reads canonical machine
authorities through the existing JeevesCompletionCensus and gate inventory.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_completion_census import JeevesCompletionCensus
from .jeeves_release_gate_inventory import JeevesReleaseGateInventory

SCHEMA = "skeleton.ai.jeeves_verification_progress.v1"
MAX_BACKLOG = 3000
MAX_PAGE = 80


def _percent(part, whole):
    """Exact two-decimal percent, no floating point approximation."""
    if (type(part) is not int or type(whole) is not int or
            whole < 0 or part < 0 or part > whole):
        raise JeevesAppwideError("progress counts outside trusted denominator")
    if not whole:
        return None
    return float((Decimal(part) * Decimal(100) / Decimal(whole)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP))


def _facet(name, verified, total, *, meaning, evidentiary):
    missing = total - verified
    return {
        "name": name,
        "verified_or_declared_count": verified,
        "denominator": total,
        "remaining": missing,
        "percent_complete": _percent(verified, total),
        "percent_remaining": _percent(missing, total),
        "semantic_layer": meaning,
        "independent_execution_evidence": evidentiary,
    }


class JeevesVerificationProgress:
    """Factual source counters; never transfer paper states into live readiness."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical scanned inventory required")
        inventory._require_scanned()
        self.inv = inventory

    def _collect(self, expected_snapshot=None, expected_census_digest=None,
                 expected_gate_digest=None):
        inv = self.inv
        census = JeevesCompletionCensus(inv).report(
            expected_snapshot=expected_snapshot)
        if (expected_census_digest is not None and
                census["digest"] != expected_census_digest):
            raise JeevesAppwideError("stale canonical AI completion census")
        release = JeevesReleaseGateInventory(inv).overview(
            expected_snapshot=expected_snapshot)
        if (expected_gate_digest is not None and
                release["digest"] != expected_gate_digest):
            raise JeevesAppwideError("stale exact-head release gate inventory")
        volume_total = census["plan"]["volume_total"]
        enterprise_qualified = census["plan"]["enterprise_qualified_volumes"]
        statuses = census["plan"]["volume_implementation_states"]
        source_verified = statuses.get("verified", 0)
        capability_total = census["ai_product"]["capability_total"]
        registry_complete = census["ai_product"]["registry_complete_count"]
        cap_states = census["ai_product"]["capability_states"]
        gaps_total = census["construction"]["gap_total"]
        gap_closed = census["construction"]["declared_closed_gaps"]
        required_paths = census["application"]["required_path_total"]
        present_paths = census["application"]["required_paths_present"]
        # A source-only census cannot assert that 0 real world tests happened.
        # It can strictly state that it has VERIFIED 0 test outcomes and that
        # their actual external completion remains UNKNOWN.
        facets = {
            "volume_implementation_metadata": _facet(
                "Machine volume implementation records marked verified",
                source_verified, volume_total,
                meaning="declared_implementation_status_only",
                evidentiary=False),
            "enterprise_volume_qualification": _facet(
                "Independently enterprise-qualified machine volumes",
                enterprise_qualified, volume_total,
                meaning="declared_enterprise_qualification",
                evidentiary=False),
            "ai_capability_registry": _facet(
                "Registry-complete product AI capabilities",
                registry_complete, capability_total,
                meaning="declared_product_implementation_state",
                evidentiary=False),
            "construction_gap_register": _facet(
                "Declared closed app-construction gaps",
                gap_closed, gaps_total,
                meaning="declared_construction_source_ledger",
                evidentiary=False),
            "required_paths": _facet(
                "Present canonical required app source paths",
                present_paths, required_paths,
                meaning="static_file_presence_only",
                evidentiary=False),
            "release_workflow_sources": _facet(
                "Present mandatory exact-head CI gate workflow files",
                release["sources_present"], release["required_gates"],
                meaning="static_workflow_source_presence_only",
                evidentiary=False),
            "verified_exact_head_ci_from_source_scan": _facet(
                "Exact-head required gates independently observed as passed in this scan",
                release["independently_verified_checks"],
                release["required_gates"],
                meaning="unknown_external_ci_result_zero_verified_by_this_scan",
                evidentiary=False),
        }
        blockers = []
        if registry_complete < capability_total:
            blockers.append("product_capability_registry_not_complete")
        if enterprise_qualified < volume_total:
            blockers.append("enterprise_volumes_not_independently_qualified")
        if gap_closed < gaps_total:
            blockers.append("declared_construction_gaps_not_all_closed")
        if present_paths < required_paths:
            blockers.append("missing_required_application_paths")
        if release["sources_present"] < release["required_gates"]:
            blockers.append("missing_required_ci_workflow_sources")
        blockers += [
            "external_exact_head_ci_results_unobserved",
            "real_installed_app_and_game_studio_acceptance_unobserved",
            "actual_model_quality_and_training_qualification_unobserved",
            "full_independent_user_journeys_unobserved",
        ]
        # The release predicate is ALWAYS false for this static-data-only
        # source scan. No untrusted caller can supply a fake passed gate list.
        ready = False
        body = {
            "schema": SCHEMA,
            "inventory_snapshot": inv._digest,
            "census_digest": census["digest"],
            "release_gate_inventory_digest": release["digest"],
            "canonical_source_files": census["source_inventory_regular_files"],
            "ai_product_capability_state_counts": cap_states,
            "masterplan_volume_implementation_state_counts": statuses,
            "masterplan_volume_enterprise_state_counts":
                census["plan"]["volume_enterprise_states"],
            "facets": facets,
            "source_declared_volume_implementation_verified_percent":
                facets["volume_implementation_metadata"]["percent_complete"],
            "declared_enterprise_qualified_percent":
                facets["enterprise_volume_qualification"]["percent_complete"],
            "enterprise_percent_remaining":
                facets["enterprise_volume_qualification"]["percent_remaining"],
            "declared_capability_complete_percent":
                facets["ai_capability_registry"]["percent_complete"],
            "capability_percent_remaining":
                facets["ai_capability_registry"]["percent_remaining"],
            "independently_verified_ci_percent_from_source_only_scan":
                facets["verified_exact_head_ci_from_source_scan"]["percent_complete"],
            "actual_external_ci_status": "not_observed",
            "actual_model_quality_status": "not_observed",
            "actual_device_and_service_acceptance": "not_observed",
            "live_product_ready": ready,
            "overall_app_completion_percent": None,
            "remaining_overall_percent": None,
            "known_blocking_categories": sorted(set(blockers)),
            "source_status_cannot_be_rebranded_as_independent_proof": True,
            "verified_release_assurance_not_inferred_from_code_presence": True,
            "source_edits_performed": False,
        }
        return {**body, "digest": digest(body)}, census, release

    def overview(self, *, expected_snapshot=None,
                 expected_census_digest=None, expected_gate_digest=None):
        report, _, _ = self._collect(
            expected_snapshot=expected_snapshot,
            expected_census_digest=expected_census_digest,
            expected_gate_digest=expected_gate_digest)
        return report

    def backlog(self, *, offset=0, limit=40,
                expected_progress_digest=None,
                expected_snapshot=None,
                expected_census_digest=None, expected_gate_digest=None):
        if type(offset) is not int or not 0 <= offset <= MAX_BACKLOG:
            raise JeevesAppwideError("bounded verification backlog offset required")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded verification backlog page required")
        report, census, release = self._collect(
            expected_snapshot=expected_snapshot,
            expected_census_digest=expected_census_digest,
            expected_gate_digest=expected_gate_digest)
        if (expected_progress_digest is not None and
                expected_progress_digest != report["digest"]):
            raise JeevesAppwideError("stale verification percentage receipt")
        tasks = []
        for cap in census["ai_product"]["capabilities"]:
            tasks.append({
                "id": "AI-CAP-" + cap["id"],
                "kind": "product_ai_qualification",
                "priority": "P0",
                "authority_owner": cap["owner"],
                "status": "unqualified",
                "source_registry_state": cap["declared_state"],
                "required_evidence": [
                    "complete canonical capability implementation",
                    "real user-facing end-to-end functional execution",
                    "independent model, permissions, performance and failure evidence",
                ],
            })
        for name, count in sorted(report[
                "masterplan_volume_enterprise_state_counts"].items()):
            if name not in ("enterprise_qualified", "superior"):
                tasks.append({
                    "id": "ENTERPRISE-STATE-" + name,
                    "kind": "enterprise_volume_grade",
                    "priority": "P0",
                    "status": "not_qualified",
                    "affected_volumes": count,
                    "required_evidence": [
                        "independent source-bound evaluation for every affected volume",
                        "validated enterprise policy, safety, benchmark and rollback",
                        "update canonical volume state only after signoff",
                    ],
                })
        for issue in release["sources_missing"] and
                     ["missing_required_release_gate_workflows"] or []:
            tasks.append({
                "id": "CI-WORKFLOW-MISSING", "kind": "required_ci_workflow",
                "priority": "P0", "status": "missing_workflow_source",
                "affected_gates": release["sources_missing"],
                "required_evidence": ["restore required workflow file authorities"],
            })
        tasks += [{
            "id": "GATE-CHECKS-EXACT-HEAD",
            "kind": "independent_ci_observation",
            "priority": "P0",
            "status": "unobserved",
            "affected_gates": release["required_gates"],
            "required_evidence": [
                "retrieve current exact-commit required check run conclusions",
                "reject queued/cancelled/stale/non-head workflow outcomes",
            ],
        }, {
            "id": "APP-INSTALLED-JOURNEYS",
            "kind": "installed_app_acceptance",
            "priority": "P0",
            "status": "unobserved",
            "required_evidence": [
                "run real assembled app on target platforms",
                "verify authenticated persistence and user journeys",
            ],
        }, {
            "id": "AI-MODEL-QUALITY",
            "kind": "trained_model_qualification",
            "priority": "P0",
            "status": "unobserved",
            "required_evidence": [
                "independent held-out product model performance",
                "reviewed failure, security and source rights outcomes",
            ],
        }]
        tasks.sort(key=lambda x: (x["priority"], x["id"]))
        page = tasks[offset:offset + limit]
        body = {
            "schema": SCHEMA + ".backlog",
            "progress_digest": report["digest"],
            "inventory_snapshot": self.inv._digest,
            "total_work_item_groups": len(tasks),
            "offset": offset, "limit": limit,
            "next_offset": offset + len(page)
                if offset + len(page) < len(tasks) else None,
            "tasks": page,
            "grouped_volume_count_is_not_one_completed_task": True,
            "source_records_do_not_self_sign": True,
            "external_results_not_read_or_fabricated": True,
            "source_mutated": False,
        }
        return {**body, "digest": digest(body)}
