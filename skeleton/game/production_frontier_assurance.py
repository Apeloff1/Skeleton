"""Six frontier game-quality augmentations: independent challenges, comparative
scorecards, keyed host receipts, owner routing, priority, and review checkpoints.

This is candidate governance, not a replacement for real native playback,
external IP counsel, signer identity attestation, or production release policy.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import hmac
import math
from typing import Any

from .production_quality import QualityGateError, _digest, _record
from .production_deep_gates import _sha
from .production_frontier_gates import FRONTIER_NAMES, audit_frontier_candidate, verify_frontier_report


_REVIEW_OWNERS = {
    "world": "world_editor", "canon": "narrative_director",
    "assets": "asset_forge", "replay": "reproducible_builder",
    "performance": "render_profiler", "rights": "human_rights_reviewer",
    "traceability": "gdd_director", "quests": "quest_director",
    "accessibility": "accessibility_designer", "controls": "input_director",
    "resources": "resource_budget_owner", "session": "gameplay_replay_owner",
    "package": "platform_build_owner", "lineage": "asset_provenance_owner",
    "continuity": "canon_director", "routes": "gameplay_qa_director",
    "physics": "physics_director", "lod": "render_lod_director",
    "localization": "localization_director", "comparison": "performance_researcher",
}
_CRITICAL = frozenset(("rights", "session", "replay", "lineage", "package", "physics"))


def prioritized_quality_work(report: Mapping[str, Any], *, limit: int = 1000) -> dict:
    """Deterministically route failures to the correct existing production owner."""
    if (not isinstance(report, Mapping) or report.get("schema") != "game.candidate.frontier_quality.v1"
            or type(report.get("findings")) is not list or
            type(limit) is not int or not 1 <= limit <= 1000):
        raise QualityGateError("valid frontier findings and bounded work queue required")
    seen = set()
    tasks = []
    for row in report["findings"]:
        if type(row) is not dict or set(row) != {"gate", "code", "subject"}:
            raise QualityGateError("malformed quality finding")
        gate, code, subject = row["gate"], row["code"], row["subject"]
        if (type(gate) is not str or gate not in _REVIEW_OWNERS or
                type(code) is not str or not 1 <= len(code) <= 128 or
                type(subject) is not str or len(subject) > 256):
            raise QualityGateError("untrusted quality issue identity")
        identity = (gate, code, subject)
        if identity in seen:
            continue
        seen.add(identity)
        tasks.append({
            "gate": gate, "code": code, "subject": subject,
            "priority": "P0" if gate in _CRITICAL else "P1",
            "owner": _REVIEW_OWNERS[gate],
            "requires_authorized_source_change": True,
            "auto_merge": False, "rights_signoff": False,
        })
    tasks.sort(key=lambda r: (r["priority"], r["gate"], r["code"], r["subject"]))
    tasks = tasks[:limit]
    payload = {
        "schema": "game.frontier.owner_work.v1",
        "source_sha256": _sha(report.get("source_digest"), "owner task source"),
        "report_sha256": _digest(dict(report)),
        "tasks": tasks, "truncated": len(seen) > len(tasks),
        "production_approved": False,
    }
    return {**payload, "receipt_digest": _digest(payload)}


def quality_report_delta(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict:
    """Objective evidence delta, source-aware, never self-certifying progress."""
    for obj in (previous, current):
        if (not isinstance(obj, Mapping) or
                obj.get("schema") != "game.candidate.frontier_quality.v1" or
                obj.get("release_certified") is not False or
                type(obj.get("gates")) is not list or
                obj.get("evidence_digest") != _digest(obj["gates"]) or
                type(obj.get("findings")) is not list or
                obj.get("candidate_passed") is not (not obj["findings"])):
            raise QualityGateError("comparative review requires internally consistent frontier reports")
        _sha(obj.get("source_digest"), "comparison source")
    a = {gate.get("name"): gate for gate in previous["gates"] if type(gate) is dict}
    b = {gate.get("name"): gate for gate in current["gates"] if type(gate) is dict}
    if (len(a) != 20 or len(b) != 20 or tuple(a) != tuple(b)
            or set(a) != set(_REVIEW_OWNERS)):
        raise QualityGateError("cannot compare incomplete or unequal 20-gate reports")
    gains = []
    losses = []
    equal = []
    for name in a:
        old_findings = len(a[name].get("findings", ()))
        new_findings = len(b[name].get("findings", ()))
        row = {"gate": name, "previous": old_findings, "current": new_findings}
        (gains if new_findings < old_findings else
         losses if new_findings > old_findings else equal).append(row)
    regressions = any(x["gate"] in _CRITICAL for x in losses)
    output = {
        "schema": "game.frontier.objective_delta.v1",
        "source_changed": previous["source_digest"] != current["source_digest"],
        "previous_source_sha256": previous["source_digest"],
        "current_source_sha256": current["source_digest"],
        "previous_evidence_sha256": previous["evidence_digest"],
        "current_evidence_sha256": current["evidence_digest"],
        "improved_gates": gains, "regressed_gates": losses,
        "unchanged_gates": equal,
        "critical_regression": regressions,
        "strict_pareto_improvement": bool(gains) and not losses,
        "production_approval": False,
    }
    return {**output, "receipt_digest": _digest(output)}


def host_attest_report(report: Mapping[str, Any], *,
                       host_secret: bytes, key_id: str, reviewer_id: str) -> dict:
    """Integrity MAC tied to host-provisioned secret, never an agent-made signature.

    Caller must independently authenticate reviewer and protect external key.
    """
    if (not isinstance(report, Mapping) or report.get("schema") != "game.candidate.frontier_quality.v1"
            or report.get("release_certified") is not False):
        raise QualityGateError("only candidate frontier evidence may be MAC-bound")
    if (type(host_secret) is not bytes or not 32 <= len(host_secret) <= 4096 or
            type(key_id) is not str or not 3 <= len(key_id) <= 128 or
            type(reviewer_id) is not str or not 3 <= len(reviewer_id) <= 128):
        raise QualityGateError("trusted host-supplied key and reviewer identifier required")
    _sha(report.get("source_digest"), "attestation source")
    if report.get("evidence_digest") != _digest(report.get("gates")):
        raise QualityGateError("reviewer report evidence digest mismatch")
    record = {
        "schema": "game.frontier.host_integrity_mac.v1",
        "source_sha256": report["source_digest"],
        "report_sha256": _digest(dict(report)),
        "key_id": key_id, "reviewer_id": reviewer_id,
        "scope": "candidate_integrity_not_signature_or_release_approval",
        "production_approved": False,
    }
    tag = hmac.new(host_secret, _digest(record).encode("ascii"), sha256).hexdigest()
    return {**record, "hmac_sha256": tag}


def verify_host_attestation(report: Mapping[str, Any], attestation: Mapping[str, Any], *,
                            host_secret: bytes) -> bool:
    if not isinstance(attestation, Mapping):
        raise QualityGateError("host attestation must be structured")
    exact = host_attest_report(
        report, host_secret=host_secret,
        key_id=attestation.get("key_id"), reviewer_id=attestation.get("reviewer_id"),
    )
    return (
        set(attestation) == set(exact)
        and all(attestation.get(k) == v for k, v in exact.items() if k != "hmac_sha256")
        and type(attestation.get("hmac_sha256")) is str
        and hmac.compare_digest(attestation["hmac_sha256"], exact["hmac_sha256"])
    )


def challenge_frontier_verifiers(bundle: Mapping[str, Any]) -> dict:
    """Seven original independent source mutations plus summary forgery review."""
    report = audit_frontier_candidate(bundle)
    if not report["candidate_passed"]:
        raise QualityGateError("red-team baseline must be a valid original candidate")
    attacks = (
        ("lineage", lambda c: c["frontier"]["lineage"]["assets"][0].update(rights="unknown")),
        ("continuity", lambda c: c["frontier"]["timeline"]["scenes"][0].update(introduces=["unresolved"])),
        ("routes", lambda c: c["frontier"]["routes"]["observations"].clear()),
        ("physics", lambda c: c["frontier"]["motion"]["frames"][1].update(velocity=[999., 0., 0.])),
        ("lod", lambda c: c["frontier"]["lod"]["observations"].clear()),
        ("localization", lambda c: c["frontier"]["localization"]["languages"][0]["strings"].clear()),
        ("comparison", lambda c: c["frontier"]["comparison"]["candidate"].update(p99_ms=1e9)),
    )
    outcomes = []
    for name, change in attacks:
        mutated = deepcopy(dict(bundle))
        try:
            change(mutated)
            result = audit_frontier_candidate(mutated)
        except (KeyError, IndexError, TypeError) as exc:
            raise QualityGateError("redteam fixture missing original game evidence") from exc
        gate = next(x for x in result["gates"] if x["name"] == name)
        if gate["passed"]:
            raise QualityGateError("adversarial gate accepted forged " + name)
        outcomes.append({
            "attack": name, "rejected": True,
            "finding_codes": sorted({x["code"] for x in gate["findings"]}),
            "evidence_sha256": gate["evidence_digest"],
        })
    forged = deepcopy(report)
    forged["findings"].append({"gate": "rights", "code": "forged", "subject": "none"})
    try:
        verify_frontier_report(bundle, forged)
    except QualityGateError:
        forgery_rejected = True
    else:
        raise QualityGateError("independent reviewer accepted altered summary")
    payload = {
        "schema": "game.frontier.dragon_adversary.v1",
        "source_sha256": report["source_digest"],
        "baseline_sha256": report["evidence_digest"],
        "attacks": outcomes, "forgery_rejected": forgery_rejected,
        "verified_mutations": len(outcomes), "weights_updated": False,
        "native_run_claimed": False, "external_rights_certified": False,
    }
    return {**payload, "receipt_digest": _digest(payload)}
