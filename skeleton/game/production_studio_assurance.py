"""Six operational upgrades for 27-gate game studio quality assurance.

Provides adversarial mutation, objective change evaluation, owner-scoped work
routing, source-preserving native witness checks, and source-based verifier
cross-examination. Existing quality journal and Jeeves host boundary remain
the only persistence and tool authorities.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .production_quality import QualityGateError, _digest
from .production_deep_gates import _sha
from .production_studio_gates import NAMES, audit_complete_studio, verify_complete_studio

OWNERS = {
    "cinematics": "cinematic_director",
    "dialogue_sync": "voice_lipsync_director",
    "npc_behaviors": "npc_behavior_director",
    "streaming": "world_streaming_owner",
    "save_migrations": "savegame_compatibility_owner",
    "dynamic_world": "dynamic_environment_director",
    "input_latency": "input_latency_owner",
}
CRITICAL = frozenset(("npc_behaviors", "streaming", "save_migrations", "dynamic_world", "input_latency"))
ALL_GATES = ("world", "canon", "assets", "replay", "performance", "rights",
             "traceability", "quests", "accessibility", "controls", "resources",
             "session", "package", "lineage", "continuity", "routes", "physics",
             "lod", "localization", "comparison") + NAMES


def verify_report_structure(report: Mapping[str, Any]) -> dict:
    """Validate claimed statuses against every gate and all source receipts."""
    if not isinstance(report, Mapping) or set(report) != {
        "schema", "source_digest", "candidate_passed", "release_certified",
        "gates", "findings", "evidence_digest",
    }:
        raise QualityGateError("studio report schema invalid")
    if (report["schema"] != "game.candidate.complete_studio.v1" or
            report["release_certified"] is not False or
            type(report["gates"]) is not list or len(report["gates"]) != 27 or
            type(report["findings"]) is not list):
        raise QualityGateError("studio report must hold 27 non-certifying gate findings")
    _sha(report.get("source_digest"), "quality report source")
    if tuple(g.get("name") for g in report["gates"] if type(g) is dict) != ALL_GATES:
        raise QualityGateError("quality report omitted or reordered a gate")
    merged = []
    for gate in report["gates"]:
        if (type(gate.get("passed")) is not bool or
                type(gate.get("findings")) is not list or
                gate["passed"] is not (not gate["findings"])):
            raise QualityGateError("quality gate lacks internally consistent outcome")
        _sha(gate.get("evidence_digest"), "gate receipt")
        for finding in gate["findings"]:
            if (type(finding) is not dict or set(finding) != {"gate", "code", "subject"}
                    or any(type(v) is not str for v in finding.values())
                    or finding["gate"] != gate["name"]):
                raise QualityGateError("quality finding contradicts its source gate")
        merged.extend(gate["findings"])
    if (report["findings"] != merged or report["candidate_passed"] is not (not merged)
            or report["evidence_digest"] != _digest(report["gates"])):
        raise QualityGateError("quality report summary inconsistent with gate evidence")
    return {
        "schema": "game.studio.structure_verified.v1",
        "source_digest": report["source_digest"],
        "gate_count": 27,
        "findings_count": len(merged),
        "evidence_sha256": report["evidence_digest"],
        "release_certified": False,
    }


def challenge_studio_verifiers(bundle: Mapping[str, Any]) -> dict:
    """Mutate each of seven new domains, then attack summary and gate evidence."""
    report = audit_complete_studio(bundle)
    verify_complete_studio(bundle, report)
    if not report["candidate_passed"]:
        raise QualityGateError("redteam requires clean source evidence baseline")
    attacks = (
        ("cinematics", lambda x: x["studio"]["cinematics"]["scenes"][0]["shots"][0].update(end_frame=0)),
        ("dialogue_sync", lambda x: x["studio"]["dialogue"]["cues"][0].update(caption_end_ms=999999)),
        ("npc_behaviors", lambda x: x["studio"]["npcs"]["agents"][0]["states"][0].update(next=["missing"])),
        ("streaming", lambda x: x["studio"]["streaming"]["chunks"][0].update(bytes=999999999)),
        ("save_migrations", lambda x: x["studio"]["saves"]["migrations"][0].update(independently_replayed=False)),
        ("dynamic_world", lambda x: x["studio"]["environment"]["observations"].clear()),
        ("input_latency", lambda x: x["studio"]["latency"]["observations"][0].update(render_ack_ms=9999999)),
    )
    evidence = []
    for name, mutator in attacks:
        trial = deepcopy(dict(bundle))
        try:
            mutator(trial)
            observed = audit_complete_studio(trial)
        except (KeyError, IndexError, TypeError, QualityGateError) as exc:
            raise QualityGateError("Dragon challenge fixture cannot be evaluated: " + name) from exc
        actual = next(g for g in observed["gates"] if g["name"] == name)
        if actual["passed"]:
            raise QualityGateError("Dragon could not reject forged " + name)
        evidence.append({
            "gate": name, "rejected": True,
            "finding_codes": sorted({f["code"] for f in actual["findings"]}),
            "modified_evidence_sha256": actual["evidence_digest"],
        })
    forged = deepcopy(report)
    forged["gates"][20]["findings"] = []
    try:
        verify_complete_studio(bundle, forged)
    except QualityGateError:
        report_forgery_rejected = True
    else:
        raise QualityGateError("independent reviewer accepted modified gate")
    forged = deepcopy(report)
    forged["candidate_passed"] = False
    try:
        verify_report_structure(forged)
    except QualityGateError:
        summary_forgery_rejected = True
    else:
        raise QualityGateError("adversarial reviewer accepted forged summary")
    result = {
        "schema": "game.studio.dragon_adversary.v1",
        "source_sha256": report["source_digest"],
        "evidence_sha256": report["evidence_digest"],
        "mutations_rejected": evidence,
        "mutations_count": len(evidence),
        "report_forgery_rejected": report_forgery_rejected,
        "summary_forgery_rejected": summary_forgery_rejected,
        "weights_updated": False,
        "real_native_run_claimed": False,
        "copyright_verified": False,
    }
    return {**result, "receipt_digest": _digest(result)}


def compare_studio_reports(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict:
    """Document honest regressions, separately flagging changed source snapshots."""
    a = verify_report_structure(previous)
    b = verify_report_structure(current)
    gained, lost, unchanged = [], [], []
    for old, new in zip(previous["gates"], current["gates"]):
        pre = len(old["findings"])
        post = len(new["findings"])
        entry = {"gate": new["name"], "before": pre, "after": post}
        (gained if post < pre else lost if post > pre else unchanged).append(entry)
    result = {
        "schema": "game.studio.objective_delta.v1",
        "source_changed": a["source_digest"] != b["source_digest"],
        "previous_source_sha256": a["source_digest"],
        "current_source_sha256": b["source_digest"],
        "improvements": gained, "regressions": lost, "unchanged": unchanged,
        "critical_regression": any(e["gate"] in CRITICAL for e in lost),
        "strict_pareto_improvement": bool(gained) and not lost,
        "candidate_passed": current["candidate_passed"],
        "native_device_measurements": False,
        "production_approved": False,
    }
    return {**result, "receipt_digest": _digest(result)}


def studio_repair_queue(report: Mapping[str, Any], *, limit: int = 512) -> dict:
    """Route outstanding work across all 27 owners; prevent auto-authorizing edits."""
    from .production_frontier_assurance import _REVIEW_OWNERS
    verify_report_structure(report)
    if type(limit) is not int or not 1 <= limit <= 512:
        raise QualityGateError("bounded repair queue needed")
    owners = dict(_REVIEW_OWNERS)
    owners.update(OWNERS)
    queue = []
    seen = set()
    for finding in report["findings"]:
        gate, code, subject = finding["gate"], finding["code"], finding["subject"]
        identity = (gate, code, subject)
        if identity in seen:
            continue
        seen.add(identity)
        queue.append({
            "gate": gate, "code": code, "subject": subject,
            "owner": owners[gate],
            "priority": "P0" if gate in CRITICAL or gate in
            ("rights", "session", "replay", "lineage", "package", "physics") else "P1",
            "requires_source_review": True,
            "authorized_to_mutate": False,
            "native_evidence_claimed": False,
        })
    queue.sort(key=lambda x: (x["priority"], x["gate"], x["code"], x["subject"]))
    result = {
        "schema": "game.studio.repair_queue.v1",
        "source_sha256": report["source_digest"],
        "evidence_sha256": report["evidence_digest"],
        "work_items": queue[:limit],
        "work_remaining": max(0, len(queue) - limit),
        "auto_repair_executed": False,
        "human_rights_review_required": True,
    }
    return {**result, "receipt_digest": _digest(result)}


def inspect_native_game_witness(bundle: Mapping[str, Any], world, traveler,
                                files: Mapping[str, str], native: Mapping[str, Any]) -> dict:
    """Bind native Godot replay to *canonical* compiled game and studio source.

    A verified native stdout replay is still not independently signed hardware
    evidence. Only the existing Godot runner can execute and capture the engine.
    """
    from skeleton.jeeves.game_frontier_expedition import ExpeditionWorld, Traveler
    from skeleton.jeeves.game_frontier_expedition_godot import verify_expedition_godot_project
    if not isinstance(world, ExpeditionWorld) or not isinstance(traveler, Traveler):
        raise QualityGateError("native witness requires typed original world and player")
    report = audit_complete_studio(bundle)
    if world.source_digest != report["source_digest"]:
        raise QualityGateError("native world source not bound to studio candidate")
    pack = verify_expedition_godot_project(
        files, world, traveler,
        include_autoplay="game/frontier/autoplay.json" in files,
    )
    from .production_quality import _digest as standard_digest
    if (not isinstance(native, Mapping) or
            native.get("schema") != "skeleton.game.expedition_native_complete_replay.v1" or
            native.get("world_digest") != world.digest or
            native.get("source_digest") != world.source_digest or
            native.get("candidate_files_receipt") != pack["receipt_digest"] or
            native.get("native_process_executed") is not True or
            native.get("native_gameplay_consistent") is not True or
            native.get("completed") is not True or
            native.get("receipt_digest") != standard_digest({
                k: v for k, v in native.items() if k != "receipt_digest"
            })):
        raise QualityGateError("native game evidence does not match compiled authored source")
    result = {
        "schema": "game.studio.native_source_witness.v1",
        "source_sha256": report["source_digest"],
        "world_sha256": world.digest,
        "candidate_file_sha256": pack["receipt_digest"],
        "quality_report_sha256": report["evidence_digest"],
        "native_receipt_sha256": native["receipt_digest"],
        "original_native_process_observed": True,
        "gpu_performance_attested": False,
        "native_origin_independently_signed": False,
        "production_approved": False,
    }
    return {**result, "receipt_digest": _digest(result)}
