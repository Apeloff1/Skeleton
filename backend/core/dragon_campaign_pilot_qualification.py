"""Read-only Dragon Atlas pilot qualification presentation.

This is a backend product projection, never a second crawler authority.
It consumes only the already verified, owner-fenced Atlas metadata. It does
not authenticate source policies, fetch URLs, schedule jobs, or grant any
release, publishing, training, or review permission.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_EXTERNAL_GATES = (
    "exact_head_merge_readiness",
    "backend_quality",
    "frontend_typecheck_and_product_e2e",
    "architecture_and_source_parity",
    "workflow_input_security",
    "codeql_and_secret_scanning",
    "malware_artifact_dependency_and_hygiene",
    "windows11_wsl2_docker_native_device",
    "crash_recovery_rollback_and_provenance",
    "human_source_rights_and_publication_review",
)
_MAX_CHECKS = 12


def _section(document: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ValueError("Dragon pilot has an incomplete trusted metadata section")
    return value


def _count(section: Mapping[str, object], field: str, *, ceiling: int = 2**31 - 1) -> int:
    value = section.get(field)
    if type(value) is not int or not 0 <= value <= ceiling:
        raise ValueError("Dragon pilot received an invalid bounded counter")
    return value


def _boolean(section: Mapping[str, object], field: str) -> bool:
    value = section.get(field)
    if type(value) is not bool:
        raise ValueError("Dragon pilot received a non-boolean authority field")
    return value


def _hash(value: object) -> bool:
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


def _stage_chain(value: object, expected: int) -> bool:
    if not isinstance(value, list) or len(value) != expected:
        return False
    return all(
        isinstance(item, Mapping)
        and item.get("ordinal") == position
        and _hash(item.get("receipt_digest"))
        and _hash(item.get("chain_digest"))
        and isinstance(item.get("name"), str)
        and 1 <= len(item["name"]) <= 128
        for position, item in enumerate(value)
    )


def qualify_dragon_pilot(report: Mapping[str, object]) -> dict[str, object]:
    """Construct a deterministic, metadata-only pilot exit packet.

    Inputs MUST come from the in-process verified Atlas response after its
    second owner/policy read. Never accept HTTP-submitted Atlas metadata as
    authority. Even an all-green local packet cannot release the application.
    """
    if not isinstance(report, Mapping) or report.get("schema_version") != (
        "skeleton.dragon.campaign_atlas_dashboard.v1"
    ):
        raise ValueError("Dragon pilot requires the canonical Atlas report")
    for key in ("atlas_digest", "snapshot_digest", "mandate_digest"):
        if not _hash(report.get(key)):
            raise ValueError("Dragon pilot has no exact source identity")
    if type(report.get("run_sequence")) is not int or report["run_sequence"] < 0:
        raise ValueError("Dragon pilot requires a canonical run sequence")
    if (
        report.get("read_only") is not True
        or report.get("network_executed") is not False
        or report.get("publication_granted") is not False
        or report.get("training_permission") is not False
        or report.get("review_required") is not True
    ):
        raise PermissionError("Atlas authority flags do not permit pilot projection")

    policy = _section(report, "source_policy")
    retrieval = _section(report, "retrieval")
    review = _section(report, "review_operations")
    forensics = _section(report, "forensics")
    operations = _section(report, "operations")
    context = _section(report, "context")
    scorecard = _section(report, "scorecard")
    similarity = _section(report, "source_similarity")
    robustness = _section(report, "retrieval_robustness")

    if (
        not _hash(policy.get("digest"))
        or not _hash(retrieval.get("digest"))
        or not _hash(operations.get("report_digest"))
        or not _hash(forensics.get("report_digest"))
        or forensics.get("atlas_digest") != report["atlas_digest"]
        or forensics.get("source_policy_digest") != policy["digest"]
        or forensics.get("retrieval_digest") != retrieval["digest"]
        or operations.get("source_snapshot_digest") != report["snapshot_digest"]
        or operations.get("run_sequence") != report["run_sequence"]
        or not _stage_chain(report.get("stages"), 26)
        or not _stage_chain(forensics.get("stages"), 26)
        or not _stage_chain(operations.get("stages"), 6)
    ):
        raise ValueError("Atlas source or forensic provenance is inconsistent")

    if (
        _boolean(context, "raw_source_text_redacted") is not True
        or _boolean(context, "fresh_policy_recheck_required") is not True
        or _boolean(forensics, "source_bodies_redacted") is not True
        or _boolean(forensics, "publication_granted") is not False
        or _boolean(forensics, "training_permission") is not False
        or _boolean(forensics, "network_or_model_invoked") is not False
        or _boolean(operations, "source_text_redacted") is not True
        or _boolean(operations, "read_only") is not True
        or _boolean(operations, "network_executed") is not False
        or _boolean(operations, "automatic_recovery_authorized") is not False
        or _boolean(similarity, "source_bodies_redacted") is not True
        or _boolean(robustness, "source_bodies_excluded") is not True
        or review.get("durable_review_mutations") is not False
        or review.get("human_review_recorded") is not False
        or scorecard.get("decision") != "human_review_hold"
    ):
        raise PermissionError("Atlas source privacy or external-effect guard failed")

    source_count = _count(policy, "sources_seen", ceiling=64)
    included = _count(policy, "included_source_count", ceiling=64)
    excluded = _count(policy, "excluded_source_count", ceiling=64)
    if included + excluded != source_count:
        raise ValueError("Dragon pilot source-policy coverage is incomplete")
    hits = _count(retrieval, "retained_hits", ceiling=32)
    hosts = _count(retrieval, "distinct_hosts", ceiling=16)
    pending_reviews = _count(review, "pending_tasks", ceiling=4096)
    blocked_reviews = _count(review, "blocked_tasks", ceiling=4096)
    total_reviews = _count(review, "tasks_total", ceiling=4096)
    if pending_reviews + blocked_reviews > total_reviews:
        raise ValueError("Dragon pilot review accounting mismatch")
    uncertain_bytes = _count(operations, "uncertain_bytes", ceiling=33_554_432)
    privacy_held = _count(forensics, "privacy_held_sources", ceiling=64)
    active_content_held = _count(forensics, "active_content_held_sources", ceiling=64)
    security_held = _count(forensics, "security_held_sources", ceiling=64)
    provenance_held = _count(forensics, "provenance_held_sources", ceiling=64)
    grounding_deficit = _count(forensics, "grounding_deficit_objectives", ceiling=8)
    query_unsupported = _count(forensics, "query_unsupported_objectives", ceiling=8)
    context_overrun = _boolean(forensics, "context_budget_exceeded")
    if type(operations.get("capacity_holds")) is not list or len(operations["capacity_holds"]) > 256:
        raise ValueError("Dragon pilot resource observations are unbounded")
    flagged = robustness.get("flagged_objectives")
    if not isinstance(flagged, list) or len(flagged) > 8:
        raise ValueError("Dragon pilot objective robustness is unbounded")

    gates = (
        ("current_policy", included > 0 and excluded == 0,
         "renew_or_review_source_permissions"),
        ("source_bound_evidence", hits > 0 and _count(forensics, "selected_passages") > 0,
         "capture_and_reinspect_reviewable_evidence"),
        ("human_review_queue", total_reviews > 0 and pending_reviews > 0 and blocked_reviews == 0,
         "resolve_blocked_or_missing_review_work"),
        ("security_and_privacy", not (privacy_held or active_content_held or security_held),
         "review_active_content_and_sensitive_evidence"),
        ("provenance_and_grounding", not (provenance_held or grounding_deficit or query_unsupported),
         "resolve_source_provenance_and_objective_gaps"),
        ("bounded_context", not context_overrun,
         "reduce_research_context_budget"),
        ("restart_custody", not (
            _boolean(operations, "pending_dispatch")
            or uncertain_bytes
            or _boolean(operations, "historical_events_incomplete")
            or _boolean(operations, "event_clock_integrity_review")
        ), "reconcile_canonical_worker_and_mongo_checkpoint"),
        ("source_robustness", hosts >= 2 and not flagged,
         "increase_independent_source_coverage"),
        ("measured_capacity", not operations["capacity_holds"]
         and _count(operations, "observed_resource_samples") > 0,
         "collect_current_resource_pressure_samples"),
        ("robots_and_origin_review", not (
            _count(operations, "unresolved_robots_origins")
            or _count(operations, "stale_robots_origins")
        ), "reauthorize_live_robots_and_origin_safety"),
    )
    if len(gates) > _MAX_CHECKS:
        raise ValueError("Dragon pilot check capacity exceeded")

    checks = [
        {"code": code, "status": "qualified" if okay else "held",
         "next_action": None if okay else action}
        for code, okay, action in gates
    ]
    blockers = [item["code"] for item in checks if item["status"] == "held"]
    ready = not blockers
    packet: dict[str, object] = {
        "schema_version": "skeleton.dragon.campaign_pilot_qualification.v1",
        "atlas_digest": report["atlas_digest"],
        "snapshot_digest": report["snapshot_digest"],
        "source_policy_digest": policy["digest"],
        "run_sequence": report["run_sequence"],
        "pilot_status": "ready_for_human_review" if ready else "held_for_repair",
        "pilot_check_count": len(checks),
        "checks": checks,
        "blocked_checks": blockers,
        "operator_actions": [item["next_action"] for item in checks
                             if item["next_action"] is not None],
        "external_release_checks": [
            {"code": code, "status": "not_qualified"} for code in _EXTERNAL_GATES
        ],
        "source_only": True,
        "read_only": True,
        "human_review_required": True,
        "network_used": False,
        "model_invoked": False,
        "source_text_included": False,
        "training_authorized": False,
        "publication_authorized": False,
        "release_authorized": False,
        "release_status": "held_until_independent_exact_head_and_device_evidence",
        "recheck_mongo_authority_before_any_followup": True,
    }
    packet["qualification_digest"] = hashlib.sha256(json.dumps(
        packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return packet
