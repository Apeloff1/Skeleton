"""Seven additional original-game production acceptance audits.

Inputs are source snapshots or observed host evidence, never implicit model
claims. Passing audits remains a candidate property, not a release signature.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
import math
import re
from typing import Any

from .production_quality import (
    Finding, GateResult, QualityGateError, _digest, _items, _record, _result,
    audit_release_candidate,
)

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_HEX = re.compile(r"^[a-f0-9]{64}$")
_CONTROLS = frozenset(("move", "interact", "confirm", "cancel", "pause"))
_ACCESSIBILITY = frozenset(("keyboard", "gamepad", "screen_reader", "subtitles"))


def _id(value: Any, label: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise QualityGateError(f"{label} requires a bounded canonical identifier")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not _HEX.fullmatch(value):
        raise QualityGateError(f"{label} requires a lowercase SHA-256 digest")
    return value


def audit_design_traceability(design: Mapping[str, Any]) -> GateResult:
    """Every declared mandatory design goal needs direct source-bound proof."""
    design = _record(design, "design")
    source = _sha(design.get("source_sha256"), "design source")
    goals = _items(design.get("goals"), "goals", 4096)
    proofs = _items(design.get("proofs"), "proofs", 8192)
    findings: list[Finding] = []
    ids: set[str] = set()
    for goal in goals:
        goal = _record(goal, "goal")
        ident = _id(goal.get("id"), "goal")
        if ident in ids:
            findings.append(Finding("traceability", "duplicate_goal", ident))
        ids.add(ident)
        if type(goal.get("mandatory")) is not bool:
            raise QualityGateError("goal mandatory status must be explicit")
    covered: set[str] = set()
    for proof in proofs:
        proof = _record(proof, "proof")
        ident = _id(proof.get("goal"), "proof goal")
        if ident not in ids:
            findings.append(Finding("traceability", "unknown_goal", ident))
        if proof.get("source_sha256") != source:
            findings.append(Finding("traceability", "foreign_source", ident))
        try:
            _sha(proof.get("artifact_sha256"), "artifact proof")
        except QualityGateError:
            findings.append(Finding("traceability", "invalid_artifact", ident))
        if proof.get("observed") is True and proof.get("source_sha256") == source:
            covered.add(ident)
    for goal in goals:
        if goal["mandatory"] and goal["id"] not in covered:
            findings.append(Finding("traceability", "unproven_goal", goal["id"]))
    if not goals:
        findings.append(Finding("traceability", "empty_design", "goals"))
    return _result("traceability", findings, design)


def audit_quest_ending_graph(campaign: Mapping[str, Any]) -> GateResult:
    """Detect impossible quest prerequisites, cycles and unearned ending coverage."""
    campaign = _record(campaign, "campaign")
    stages = _items(campaign.get("stages"), "quest stages", 4096)
    endings = _items(campaign.get("endings"), "endings", 128)
    outcomes = _items(campaign.get("playthroughs"), "playthroughs", 1024)
    findings: list[Finding] = []
    graph: dict[str, tuple[str, ...]] = {}
    for stage in stages:
        stage = _record(stage, "stage")
        ident = _id(stage.get("id"), "stage")
        reqs = _items(stage.get("requires", []), "requires", 128)
        deps = tuple(_id(x, "prerequisite") for x in reqs)
        if ident in graph:
            findings.append(Finding("quests", "duplicate_stage", ident))
        graph[ident] = deps
    for key, deps in graph.items():
        if key in deps or any(d not in graph for d in deps):
            findings.append(Finding("quests", "invalid_dependency", key))
    # Kahn's algorithm bounds deeply nested quest chains without recursion.
    remaining = {key: len(set(d for d in deps if d in graph))
                 for key, deps in graph.items()}
    dependents: dict[str, set[str]] = {key: set() for key in graph}
    for key, deps in graph.items():
        for dependency in deps:
            if dependency in graph:
                dependents[dependency].add(key)
    ready = deque(sorted(key for key, count in remaining.items() if count == 0))
    while ready:
        node = ready.popleft()
        for dependent in sorted(dependents[node]):
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    for node, count in sorted(remaining.items()):
        if count:
            findings.append(Finding("quests", "dependency_cycle", node))
    covered: set[str] = set()
    ids: set[str] = set()
    for ending in endings:
        ending = _record(ending, "ending")
        ident = _id(ending.get("id"), "ending")
        if ident in ids:
            findings.append(Finding("quests", "duplicate_ending", ident))
        ids.add(ident)
        for req in _items(ending.get("requires", []), "ending requires", 128):
            if _id(req, "ending prerequisite") not in graph:
                findings.append(Finding("quests", "impossible_ending", ident))
    for episode in outcomes:
        episode = _record(episode, "playthrough")
        eid = _id(episode.get("ending"), "earned ending")
        completed = set(_id(v, "completed stage") for v in _items(episode.get("completed", []), "completed", 4096))
        if episode.get("won") is not True:
            findings.append(Finding("quests", "not_won", eid))
            continue
        ending = next((e for e in endings if e["id"] == eid), None)
        if ending is None or not set(ending.get("requires", [])) <= completed:
            findings.append(Finding("quests", "unearned_ending", eid))
        elif all(set(graph.get(node, ())) <= completed for node in completed if node in graph):
            covered.add(eid)
        else:
            findings.append(Finding("quests", "unearned_stage", eid))
    for ending in endings:
        if ending["id"] not in covered:
            findings.append(Finding("quests", "uncovered_ending", ending["id"]))
    if not endings:
        findings.append(Finding("quests", "missing_endings", "campaign"))
    return _result("quests", findings, campaign)


def audit_accessibility_ui(screens: list[dict]) -> GateResult:
    """Interactive UI must declare readable semantics, keyboard access and contrast."""
    screens = _items(screens, "screens", 2048)
    findings: list[Finding] = []
    seen: set[str] = set()
    for screen in screens:
        screen = _record(screen, "screen")
        sid = _id(screen.get("id"), "screen")
        if sid in seen:
            findings.append(Finding("accessibility", "duplicate_screen", sid))
        seen.add(sid)
        controls = _items(screen.get("controls"), "controls", 1024)
        for c in controls:
            c = _record(c, "control")
            cid = _id(c.get("id"), "control")
            label = c.get("label")
            if type(label) is not str or not label.strip():
                findings.append(Finding("accessibility", "missing_label", f"{sid}:{cid}"))
            if c.get("focusable") is not True:
                findings.append(Finding("accessibility", "not_focusable", f"{sid}:{cid}"))
            contrast = c.get("contrast_ratio")
            if (type(contrast) not in (int, float) or not math.isfinite(contrast)
                    or contrast < 4.5):
                findings.append(Finding("accessibility", "low_contrast", f"{sid}:{cid}"))
        if screen.get("subtitles") is not True:
            findings.append(Finding("accessibility", "subtitles_disabled", sid))
    if not screens:
        findings.append(Finding("accessibility", "missing_screens", "screens"))
    return _result("accessibility", findings, screens)


def audit_input_parity(profiles: list[dict]) -> GateResult:
    """Require basic gameplay semantics on keyboard and controller profiles."""
    profiles = _items(profiles, "profiles", 256)
    findings: list[Finding] = []
    devices: set[str] = set()
    for profile in profiles:
        profile = _record(profile, "profile")
        device = _id(profile.get("device"), "input device")
        if device in devices:
            findings.append(Finding("controls", "duplicate_device", device))
        devices.add(device)
        mapping = _record(profile.get("bindings"), "bindings")
        for action in sorted(_CONTROLS):
            binding = mapping.get(action)
            if type(binding) is not str or not binding.strip() or len(binding) > 128:
                findings.append(Finding("controls", "missing_action", f"{device}:{action}"))
        used: set[str] = set()
        for action, binding in mapping.items():
            _id(action, "action")
            if type(binding) is str and binding:
                if binding in used:
                    findings.append(Finding("controls", "ambiguous_binding", device))
                used.add(binding)
    for required in ("keyboard", "gamepad"):
        if required not in devices:
            findings.append(Finding("controls", "missing_profile", required))
    return _result("controls", findings, profiles)


def audit_resource_envelopes(envelopes: list[dict]) -> GateResult:
    """Bound portable RAM, loading, streaming, and texture demands by device."""
    envelopes = _items(envelopes, "envelopes", 256)
    findings: list[Finding] = []
    seen: set[str] = set()
    for e in envelopes:
        e = _record(e, "envelope")
        ident = _id(e.get("target"), "hardware target")
        if ident in seen:
            findings.append(Finding("resources", "duplicate_target", ident))
        seen.add(ident)
        for field in ("ram_mb", "texture_mb", "peak_streaming_mb", "load_ms"):
            value = e.get(field)
            limit = e.get("max_" + field)
            if (type(value) not in (int, float) or type(limit) not in (int, float)
                    or not math.isfinite(value) or not math.isfinite(limit) or
                    value < 0 or limit <= 0):
                raise QualityGateError(f"invalid hardware budget {field}")
            if value > limit:
                findings.append(Finding("resources", "budget_exceeded", ident + ":" + field))
    if not envelopes:
        findings.append(Finding("resources", "no_hardware_targets", "envelopes"))
    return _result("resources", findings, envelopes)


def audit_session_receipts(session: Mapping[str, Any]) -> GateResult:
    """Cross-check event order, state hashes and chain continuity from a pinned genesis."""
    session = _record(session, "session")
    genesis = _sha(session.get("genesis"), "session genesis")
    events = _items(session.get("events"), "events", 100000)
    findings: list[Finding] = []
    prior = genesis
    for index, event in enumerate(events, 1):
        event = _record(event, "event")
        if event.get("sequence") != index or type(event.get("sequence")) is not int:
            findings.append(Finding("session", "sequence_gap", str(index)))
        if event.get("previous") != prior:
            findings.append(Finding("session", "chain_break", str(index)))
        try:
            _sha(event.get("state_sha256"), "state digest")
        except QualityGateError:
            findings.append(Finding("session", "unbound_state", str(index)))
        claimed = event.get("receipt")
        expected = _digest({k: v for k, v in event.items() if k != "receipt"})
        if claimed != expected:
            findings.append(Finding("session", "invalid_receipt", str(index)))
        prior = expected
    if session.get("head") != prior:
        findings.append(Finding("session", "head_mismatch", "session"))
    if not events:
        findings.append(Finding("session", "empty_session", "session"))
    return _result("session", findings, session)


def audit_package_closure(package: Mapping[str, Any]) -> GateResult:
    """Validate dependency closure, orphaned objects, cycles and source lock."""
    package = _record(package, "package")
    root = _id(package.get("entry"), "entrypoint")
    files = _items(package.get("files"), "files", 10000)
    findings: list[Finding] = []
    graph: dict[str, tuple[str, ...]] = {}
    for f in files:
        f = _record(f, "file")
        fid = _id(f.get("id"), "file id")
        if fid in graph:
            findings.append(Finding("package", "duplicate_file", fid))
        try:
            _sha(f.get("sha256"), "file source")
        except QualityGateError:
            findings.append(Finding("package", "missing_hash", fid))
        graph[fid] = tuple(_id(v, "dependency") for v in _items(f.get("imports", []), "imports", 256))
    if root not in graph:
        findings.append(Finding("package", "missing_entry", root))
    reached: set[str] = set()
    pending = deque([root]) if root in graph else deque()
    while pending:
        node = pending.popleft()
        if node in reached:
            continue
        reached.add(node)
        for dependency in graph[node]:
            if dependency not in graph:
                findings.append(Finding("package", "missing_dependency", node + ":" + dependency))
            elif dependency not in reached:
                pending.append(dependency)
    for unused in sorted(set(graph) - reached):
        findings.append(Finding("package", "orphan_file", unused))
    remaining = {key: len(set(d for d in deps if d in graph))
                 for key, deps in graph.items()}
    dependents: dict[str, set[str]] = {key: set() for key in graph}
    for key, deps in graph.items():
        for dep in deps:
            if dep in graph:
                dependents[dep].add(key)
    ready = deque(sorted(key for key, count in remaining.items() if count == 0))
    while ready:
        node = ready.popleft()
        for dependent in sorted(dependents[node]):
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    for node, count in sorted(remaining.items()):
        if count:
            findings.append(Finding("package", "dependency_cycle", node))
    return _result("package", findings, package)


def audit_deep_candidate(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Compose original and seven added gates without granting release authority."""
    bundle = _record(bundle, "candidate")
    baseline = audit_release_candidate(bundle)
    audits = (
        audit_design_traceability(bundle.get("design")),
        audit_quest_ending_graph(bundle.get("campaign")),
        audit_accessibility_ui(bundle.get("screens")),
        audit_input_parity(bundle.get("profiles")),
        audit_resource_envelopes(bundle.get("envelopes")),
        audit_session_receipts(bundle.get("session")),
        audit_package_closure(bundle.get("package")),
    )
    gates = baseline["gates"] + [a.as_dict() for a in audits]
    findings = baseline["findings"] + [f.as_dict() for a in audits for f in a.findings]
    return {
        "schema": "game.candidate.deep_quality.v1",
        "source_digest": _sha(bundle.get("source_sha256"), "candidate source"),
        "candidate_passed": not findings,
        "release_certified": False,
        "gates": gates,
        "findings": findings,
        "evidence_digest": _digest(gates),
    }


def verify_deep_quality_report(bundle: Mapping[str, Any], report: Mapping[str, Any]) -> dict:
    """Independently re-execute all thirteen gates against exact original inputs.

    Neither hash correctness nor a second self-authored summary alone suffices:
    every finding, gate outcome and source identity must match recomputation.
    """
    if not isinstance(report, Mapping) or set(report) != {
        "schema", "source_digest", "candidate_passed", "release_certified",
        "gates", "findings", "evidence_digest",
    }:
        raise QualityGateError("quality verifier received a malformed report")
    actual = audit_deep_candidate(bundle)
    if dict(report) != actual:
        raise QualityGateError("independent reviewer rejected contradictory quality evidence")
    return {
        "schema": "game.candidate.independent_verify.v1",
        "source_digest": actual["source_digest"],
        "gate_count": len(actual["gates"]),
        "findings_count": len(actual["findings"]),
        "independent_replay_passed": True,
        "candidate_passed": actual["candidate_passed"],
        "release_certified": False,
        "receipt_digest": _digest(actual),
    }
