"""Comparative, adversarial and triage utilities for advanced 34-gate studio evidence.

Derived reports cannot authorize code edits, native capture, artifact publication,
memory/weight updates, rights acceptance or production signoff.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .production_quality import QualityGateError, _digest
from .production_deep_gates import _sha
from .production_studio_assurance import ALL_GATES, CRITICAL, OWNERS
from .production_advanced_gates import NAMES, audit_advanced_studio, verify_advanced_studio


NEW_OWNERS = {
    "audio_mix": "soundscape_director",
    "procedural_replay": "procedural_world_compiler",
    "economy_integrity": "economy_simulator",
    "multiplayer_sync": "network_determinism_owner",
    "transport_paths": "multi_modal_navigation_owner",
    "privacy_consent": "privacy_telemetry_owner",
    "endurance_recovery": "longform_recovery_owner",
}
CRITICAL_ADVANCED = frozenset((
    "economy_integrity", "multiplayer_sync",
    "privacy_consent", "endurance_recovery",
))
GATES_34 = ALL_GATES + NAMES

# This is an advisory read-only dependency graph, not a new execution plane.
IMPACTS = {
    "audio_mix": ("cinematics", "dialogue_sync", "accessibility"),
    "procedural_replay": ("world", "canon", "streaming", "save_migrations"),
    "economy_integrity": ("quests", "save_migrations"),
    "multiplayer_sync": ("replay", "input_latency", "save_migrations"),
    "transport_paths": ("routes", "streaming", "dynamic_world"),
    "privacy_consent": ("rights", "session", "lineage"),
    "endurance_recovery": ("session", "performance", "streaming"),
}


def verify_advanced_report_structure(report: Mapping[str, Any]) -> dict:
    """Reject forged gate count, order, status, findings, receipts and release."""
    if not isinstance(report, dict) or set(report) != {
        "schema", "source_digest", "candidate_passed",
        "release_certified", "gates", "findings", "evidence_digest",
    }:
        raise QualityGateError("34-gate report must carry exact canonical keys")
    if (report["schema"] != "game.candidate.advanced_studio.v1"
            or report["release_certified"] is not False
            or type(report["gates"]) is not list
            or len(report["gates"]) != len(GATES_34)
            or type(report["findings"]) is not list):
        raise QualityGateError("advanced quality report shape is invalid")
    _sha(report["source_digest"], "source")
    names = []
    merged = []
    for gate in report["gates"]:
        if type(gate) is not dict or set(gate) != {
                "name", "passed", "findings", "evidence_digest"}:
            raise QualityGateError("quality component must be a complete gate")
        names.append(gate["name"])
        if (type(gate["passed"]) is not bool
                or type(gate["findings"]) is not list
                or gate["passed"] is not (not gate["findings"])):
            raise QualityGateError("gate outcome conflicts with its findings")
        _sha(gate["evidence_digest"], "component evidence")
        for item in gate["findings"]:
            if (type(item) is not dict or set(item) != {"gate", "code", "subject"}
                    or any(type(x) is not str or not x for x in item.values())
                    or item["gate"] != gate["name"]):
                raise QualityGateError("finding does not belong to gate")
            merged.append(item)
    if tuple(names) != GATES_34:
        raise QualityGateError("missing, extra or reordered source quality plane")
    if (report["findings"] != merged
            or type(report["candidate_passed"]) is not bool
            or report["candidate_passed"] is not (not merged)
            or report["evidence_digest"] != _digest(report["gates"])):
        raise QualityGateError("report summary or receipt was forged")
    result = {
        "schema": "game.studio.advanced_structure_verified.v1",
        "source_sha256": report["source_digest"],
        "gate_count": len(GATES_34),
        "findings_count": len(merged),
        "evidence_sha256": report["evidence_digest"],
        "release_certified": False,
    }
    return {**result, "receipt_digest": _digest(result)}


def challenge_advanced_studio(bundle: Mapping[str, Any]) -> dict:
    """Attack each new gate, summary and independent verifier separately."""
    baseline = audit_advanced_studio(bundle)
    verify_advanced_studio(bundle, baseline)
    verify_advanced_report_structure(baseline)
    if not baseline["candidate_passed"]:
        raise QualityGateError("Dragon needs a clean candidate to probe false acceptances")
    attacks = (
        ("audio_mix", lambda d: d["studio"]["advanced"]["audio"]["observations"][0].update(true_peak_dbfs=3)),
        ("procedural_replay", lambda d: d["studio"]["advanced"]["procedural"]["generators"][0]["seeds"][0].update(replay_sha256="f" * 64)),
        ("economy_integrity", lambda d: d["studio"]["advanced"]["economy"]["transactions"][0]["entries"][0].update(amount=99)),
        ("multiplayer_sync", lambda d: d["studio"]["advanced"]["multiplayer"]["frames"][0].update(state_sha256="f" * 64)),
        ("transport_paths", lambda d: d["studio"]["advanced"]["transport"]["links"][0].update(to="nonexistent")),
        ("privacy_consent", lambda d: d["studio"]["advanced"]["privacy"]["observations"][0].update(consent=False, emitted=True)),
        ("endurance_recovery", lambda d: d["studio"]["advanced"]["endurance"]["samples"][0].update(resident_mb=999999)),
    )
    witnessed = []
    for name, mutation in attacks:
        candidate = deepcopy(dict(bundle))
        mutation(candidate)
        result = audit_advanced_studio(candidate)
        component = next(g for g in result["gates"] if g["name"] == name)
        if component["passed"]:
            raise QualityGateError("Dragon could not reject invalid " + name)
        witnessed.append({
            "gate": name,
            "rejected": True,
            "finding_codes": sorted({f["code"] for f in component["findings"]}),
            "mutated_evidence_sha256": component["evidence_digest"],
        })
    forged = deepcopy(baseline)
    forged["gates"][-1]["passed"] = False
    try:
        verify_advanced_studio(bundle, forged)
    except QualityGateError:
        independent_forgery_rejected = True
    else:
        raise QualityGateError("source verification accepted an altered gate")
    forged = deepcopy(baseline)
    forged["candidate_passed"] = False
    try:
        verify_advanced_report_structure(forged)
    except QualityGateError:
        summary_forgery_rejected = True
    else:
        raise QualityGateError("structural reviewer accepted forged summary")
    result = {
        "schema": "game.studio.advanced_dragon_challenge.v1",
        "source_sha256": baseline["source_digest"],
        "baseline_evidence_sha256": baseline["evidence_digest"],
        "attacks": witnessed,
        "attacks_rejected": len(witnessed),
        "independent_forgery_rejected": independent_forgery_rejected,
        "summary_forgery_rejected": summary_forgery_rejected,
        "weight_updates": False,
        "production_certified": False,
    }
    return {**result, "receipt_digest": _digest(result)}


def compare_advanced_studio_reports(prior: Mapping[str, Any],
                                    current: Mapping[str, Any]) -> dict:
    """Pareto comparison of every original gate; flag even one regression."""
    verify_advanced_report_structure(prior)
    verify_advanced_report_structure(current)
    better, worse, equal = [], [], []
    for old, new in zip(prior["gates"], current["gates"], strict=True):
        if old["name"] != new["name"]:
            raise QualityGateError("cross-gate comparison forbidden")
        before, after = len(old["findings"]), len(new["findings"])
        record = {"gate": new["name"], "before": before, "after": after}
        (better if after < before else worse if after > before else equal).append(record)
    result = {
        "schema": "game.studio.advanced_objective_delta.v1",
        "prior_source_sha256": prior["source_digest"],
        "current_source_sha256": current["source_digest"],
        "source_changed": prior["source_digest"] != current["source_digest"],
        "improvements": better,
        "regressions": worse,
        "unchanged": equal,
        "critical_regression": any(x["gate"] in CRITICAL | CRITICAL_ADVANCED for x in worse),
        "strict_pareto_improvement": bool(better) and not worse,
        "candidate_passed": current["candidate_passed"],
        "promotion_authorized": False,
    }
    return {**result, "receipt_digest": _digest(result)}


def advanced_studio_work_queue(report: Mapping[str, Any], *, limit: int = 256) -> dict:
    """Deduplicate and prioritize 34-gate findings without authorizing changes."""
    from .production_frontier_assurance import _REVIEW_OWNERS
    verify_advanced_report_structure(report)
    if type(limit) is not int or not 1 <= limit <= 512:
        raise QualityGateError("work limit must be 1..512")
    owners = {**_REVIEW_OWNERS, **OWNERS, **NEW_OWNERS}
    work = []
    seen = set()
    for finding in report["findings"]:
        key = (finding["gate"], finding["code"], finding["subject"])
        if key in seen:
            continue
        seen.add(key)
        gate, code, subject = key
        work.append({
            "gate": gate, "code": code, "subject": subject,
            "owner": owners[gate],
            "priority": "P0" if gate in CRITICAL | CRITICAL_ADVANCED |
                {"rights", "session", "replay", "lineage", "package", "physics"} else "P1",
            "requires_host_authorization": True,
            "auto_mutation_executed": False,
        })
    work.sort(key=lambda x: (x["priority"], x["gate"], x["code"], x["subject"]))
    result = {
        "schema": "game.studio.advanced_repair_queue.v1",
        "source_sha256": report["source_digest"],
        "evidence_sha256": report["evidence_digest"],
        "items": work[:limit],
        "remaining": max(0, len(work) - limit),
        "auto_mutation_executed": False,
    }
    return {**result, "receipt_digest": _digest(result)}


def advanced_studio_impact_graph(report: Mapping[str, Any]) -> dict:
    """Source-scoped graph of implicated upstream contracts and accountable owners."""
    verify_advanced_report_structure(report)
    failed = {g["name"] for g in report["gates"] if not g["passed"]}
    implicated = sorted({gate for name in failed & set(IMPACTS)
                         for gate in IMPACTS[name]})
    result = {
        "schema": "game.studio.advanced_quality_impact.v1",
        "source_sha256": report["source_digest"],
        "evidence_sha256": report["evidence_digest"],
        "root_issues": sorted(failed & set(IMPACTS)),
        "upstream_contracts_to_revalidate": implicated,
        "dependency_edges": [
            {"from": gate, "to": target}
            for gate in sorted(failed & set(IMPACTS))
            for target in IMPACTS[gate]
        ],
        "mutation_authorized": False,
        "release_certified": False,
    }
    return {**result, "receipt_digest": _digest(result)}
