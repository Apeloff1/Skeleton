"""Fifty independent original-game candidate evidence domains (quality gates 35-84).

Shared bounded validation kernels are parameterized by immutable domain contracts;
every gate has its own owner, evidence payload, receipt, rejection reasons and
adversarial regression. Candidate observations are not hardware attestations.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .production_quality import Finding, GateResult, QualityGateError, _digest, _items, _record, _result
from .production_deep_gates import _id, _sha
from .production_studio_gates import _number, _positive_int, _source
from .production_advanced_gates import audit_advanced_studio


@dataclass(frozen=True, slots=True)
class DomainSpec:
    name: str
    mode: str
    unit: str
    threshold: float
    owner: str


_SPECS = (
    ("frame_interpolation", "timing", "ms", 2, "render_timing_owner"),
    ("animation_blends", "timing", "ms", 8, "animation_director"),
    ("lip_transitions", "timing", "ms", 12, "voice_lipsync_director"),
    ("subtitle_layout", "timing", "ms", 40, "localization_director"),
    ("quest_causality", "timing", "ms", 250, "narrative_director"),
    ("npc_reactions", "timing", "ms", 120, "npc_behavior_director"),
    ("weather_dwell", "timing", "ms", 500, "dynamic_environment_director"),
    ("camera_path", "timing", "ms", 16, "cinematic_director"),
    ("audio_beat_grid", "timing", "ms", 20, "soundscape_director"),
    ("controller_buffer", "timing", "ms", 24, "input_latency_owner"),
    ("elastic_skin", "physics", "strain_ratio", 0.06, "character_physics_owner"),
    ("skeletal_joint", "physics", "degrees", 3, "animation_physics_owner"),
    ("center_mass", "physics", "meters", 0.04, "physics_solver_owner"),
    ("fluid_buoyancy", "physics", "newtons", 15, "fluid_physics_owner"),
    ("freefall_terminal", "physics", "meters_per_second", 1.5, "aerial_physics_owner"),
    ("wind_drafting", "physics", "newtons", 12, "aerial_physics_owner"),
    ("turbulence", "physics", "meters_per_second_squared", 1, "weather_physics_owner"),
    ("surface_grip", "physics", "slip_ratio", 0.08, "traction_physics_owner"),
    ("inertial_gyro", "physics", "degrees", 1.2, "navigation_instruments_owner"),
    ("sextant_fix", "physics", "meters", 6, "navigation_instruments_owner"),
    ("plot_threads", "graph", "nodes", 128, "narrative_director"),
    ("character_arcs", "graph", "nodes", 256, "character_director"),
    ("dialogue_choices", "graph", "nodes", 512, "dialogue_director"),
    ("quest_dependency", "graph", "nodes", 1024, "quest_director"),
    ("reputational_effects", "graph", "nodes", 256, "reputation_director"),
    ("faction_branching", "graph", "nodes", 512, "faction_director"),
    ("ending_resolutions", "graph", "nodes", 512, "narrative_director"),
    ("lore_citations", "graph", "nodes", 2048, "canon_director"),
    ("world_portals", "graph", "nodes", 1024, "multiworld_director"),
    ("multi_world_state", "graph", "nodes", 1024, "multiworld_director"),
    ("sprite_atlases", "asset", "percentage", 1, "sprite_asset_director"),
    ("color_palette", "asset", "delta_e", 3, "palette_director"),
    ("material_shaders", "asset", "percentage", 3, "shader_director"),
    ("foliage_detail", "asset", "percentage", 7, "environment_asset_director"),
    ("parallax_depth", "asset", "percentage", 4, "camera_art_director"),
    ("lod_transition", "asset", "percentage", 4, "lod_director"),
    ("shadow_contact", "asset", "percentage", 3, "lighting_director"),
    ("volumetric_light", "asset", "percentage", 5, "lighting_director"),
    ("texture_streaming", "asset", "percentage", 2, "texture_director"),
    ("particle_fidelity", "asset", "percentage", 8, "vfx_director"),
    ("checkpoint_atomic", "integrity", "ms", 750, "recovery_owner"),
    ("save_rollback", "integrity", "ms", 1250, "savegame_compatibility_owner"),
    ("chunk_receipts", "integrity", "ms", 150, "frame_evidence_owner"),
    ("deterministic_compilation", "integrity", "ms", 2000, "builder_graph_owner"),
    ("controller_binding", "integrity", "ms", 350, "input_devices_owner"),
    ("console_portability", "integrity", "ms", 5000, "cross_console_owner"),
    ("multiplayer_reconcile", "integrity", "ms", 600, "network_determinism_owner"),
    ("crawler_knowledge", "integrity", "ms", 5000, "dragon_knowledge_owner"),
    ("adversarial_promotion", "integrity", "ms", 10000, "verification_owner"),
    ("background_workers", "integrity", "ms", 15000, "longform_recovery_owner"),
)
SPECS = tuple(DomainSpec(*entry) for entry in _SPECS)
NAMES = tuple(spec.name for spec in SPECS)
OWNERS = {spec.name: spec.owner for spec in SPECS}
CRITICAL = frozenset((
    "checkpoint_atomic", "save_rollback", "chunk_receipts",
    "deterministic_compilation", "multiplayer_reconcile",
    "crawler_knowledge", "adversarial_promotion", "background_workers",
    "quest_dependency", "ending_resolutions", "world_portals",
))


def _receipt(sample: Mapping, spec: DomainSpec, source_sha256: str, subject: str,
             findings: list[Finding]) -> None:
    if sample.get("source_sha256") != source_sha256:
        findings.append(Finding(spec.name, "foreign_source", subject))
    _sha(sample.get("capture_sha256"), spec.name + " observed capture")
    if sample.get("independently_observed") is not True:
        findings.append(Finding(spec.name, "unverified_observation", subject))


def _timing(spec: DomainSpec, data: Mapping, source_sha256: str) -> list[Finding]:
    samples = _items(data.get("samples"), spec.name + " timelines", 4096)
    findings: list[Finding] = []
    seen: set[str] = set()
    previous = -1.0
    for sample in samples:
        s = _record(sample, "timing observation")
        sid = _id(s.get("id"), "timing id")
        _receipt(s, spec, source_sha256, sid, findings)
        if sid in seen:
            findings.append(Finding(spec.name, "duplicate_timing_id", sid))
        seen.add(sid)
        start = _number(s.get("start_ms"), "start_ms", high=1e12)
        end = _number(s.get("end_ms"), "end_ms", high=1e12)
        target = _number(s.get("target_end_ms"), "target_end_ms", high=1e12)
        if start < previous:
            findings.append(Finding(spec.name, "out_of_order_timing", sid))
        previous = start
        if not start < end or abs(end - target) > spec.threshold:
            findings.append(Finding(spec.name, "timing_budget_exceeded", sid))
    if len(samples) < 3:
        findings.append(Finding(spec.name, "missing_temporal_coverage", spec.name))
    return findings


def _physics(spec: DomainSpec, data: Mapping, source_sha256: str) -> list[Finding]:
    samples = _items(data.get("samples"), spec.name + " physical observations", 4096)
    findings: list[Finding] = []
    seen: set[str] = set()
    for sample in samples:
        s = _record(sample, "physical observation")
        sid = _id(s.get("id"), "measurement id")
        _receipt(s, spec, source_sha256, sid, findings)
        if sid in seen:
            findings.append(Finding(spec.name, "duplicate_measurement", sid))
        seen.add(sid)
        if s.get("unit") != spec.unit:
            findings.append(Finding(spec.name, "measurement_unit_mismatch", sid))
        expected = _number(s.get("expected"), "physical reference", low=-1e9, high=1e9)
        measured = _number(s.get("measured"), "physical measurement", low=-1e9, high=1e9)
        replay = _number(s.get("replayed"), "physical independent replay", low=-1e9, high=1e9)
        if abs(measured - expected) > spec.threshold:
            findings.append(Finding(spec.name, "physical_error_budget", sid))
        if abs(measured - replay) > spec.threshold or s.get("replay_independent") is not True:
            findings.append(Finding(spec.name, "physical_replay_divergence", sid))
    if len(samples) < 3:
        findings.append(Finding(spec.name, "insufficient_physics_coverage", spec.name))
    return findings


def _graph(spec: DomainSpec, data: Mapping, source_sha256: str) -> list[Finding]:
    nodes = _items(data.get("nodes"), spec.name + " causal graph", int(spec.threshold))
    start = _id(data.get("entry"), spec.name + " entry")
    findings: list[Finding] = []
    graph: dict[str, set[str]] = {}
    terminal: set[str] = set()
    for node in nodes:
        n = _record(node, "causal node")
        ident = _id(n.get("id"), "causal node id")
        _receipt(n, spec, source_sha256, ident, findings)
        if ident in graph:
            findings.append(Finding(spec.name, "duplicate_causal_id", ident))
        children = _items(n.get("next"), "causal transitions", 64)
        graph[ident] = {_id(x, "causal target") for x in children}
        if n.get("terminal") is True:
            terminal.add(ident)
            if children:
                findings.append(Finding(spec.name, "terminal_has_outgoing", ident))
        elif n.get("terminal") is not False:
            findings.append(Finding(spec.name, "missing_terminal_policy", ident))
        _sha(n.get("canon_sha256"), "causal canon receipt")
    if start not in graph:
        findings.append(Finding(spec.name, "missing_entry", start))
    if len(graph) < 3 or not terminal:
        findings.append(Finding(spec.name, "incomplete_causal_graph", spec.name))
    reverse: dict[str, set[str]] = {key: set() for key in graph}
    for at, children in graph.items():
        for target in children:
            if target not in graph:
                findings.append(Finding(spec.name, "dangling_causal_reference", at + ":" + target))
            else:
                reverse[target].add(at)
        if at not in terminal and not children:
            findings.append(Finding(spec.name, "unresolved_causal_dead_end", at))
    seen = {start}
    queue = deque([start])
    while queue:
        for nxt in graph.get(queue.popleft(), ()):
            if nxt in graph and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    for unreachable in sorted(set(graph) - seen):
        findings.append(Finding(spec.name, "unreachable_story_state", unreachable))
    reaches_end = set(terminal)
    queue = deque(sorted(terminal))
    while queue:
        for prev in reverse[queue.popleft()]:
            if prev not in reaches_end:
                reaches_end.add(prev)
                queue.append(prev)
    for unresolved in sorted(set(graph) - reaches_end):
        findings.append(Finding(spec.name, "unresolved_story_state", unresolved))
    return findings


def _asset(spec: DomainSpec, data: Mapping, source_sha256: str) -> list[Finding]:
    assets = _items(data.get("assets"), spec.name + " authored assets", 4096)
    max_asset_bytes = _positive_int(data.get("max_asset_bytes"), "asset memory budget", high=2**34)
    findings: list[Finding] = []
    seen: set[str] = set()
    for asset in assets:
        a = _record(asset, "authored asset")
        aid = _id(a.get("id"), "asset identity")
        _receipt(a, spec, source_sha256, aid, findings)
        if aid in seen:
            findings.append(Finding(spec.name, "duplicate_asset", aid))
        seen.add(aid)
        _sha(a.get("original_sha256"), "original authored source")
        _sha(a.get("rendered_sha256"), "rendered asset")
        if a.get("unit") != spec.unit:
            findings.append(Finding(spec.name, "asset_unit_mismatch", aid))
        if _number(a.get("deviation"), "visual deviation", high=1e6) > spec.threshold:
            findings.append(Finding(spec.name, "fidelity_regression", aid))
        if _positive_int(a.get("bytes"), "resident asset bytes", high=2**34) > max_asset_bytes:
            findings.append(Finding(spec.name, "asset_memory_budget", aid))
        if a.get("provenance_reviewed") is not True:
            findings.append(Finding(spec.name, "asset_rights_unreviewed", aid))
    if len(assets) < 2:
        findings.append(Finding(spec.name, "missing_asset_coverage", spec.name))
    return findings


def _integrity(spec: DomainSpec, data: Mapping, source_sha256: str) -> list[Finding]:
    attempts = _items(data.get("attempts"), spec.name + " replay attempts", 4096)
    findings: list[Finding] = []
    last_state: str | None = None
    seen: set[str] = set()
    for seq, attempt in enumerate(attempts, 1):
        a = _record(attempt, "state transition attempt")
        aid = _id(a.get("id"), "state attempt id")
        _receipt(a, spec, source_sha256, aid, findings)
        if aid in seen:
            findings.append(Finding(spec.name, "duplicate_attempt", aid))
        seen.add(aid)
        before = _sha(a.get("before_sha256"), "before state")
        after = _sha(a.get("after_sha256"), "after state")
        replay = _sha(a.get("replay_sha256"), "replayed after state")
        _sha(a.get("receipt_sha256"), "transition receipt")
        if a.get("generation") != seq or (last_state is not None and before != last_state):
            findings.append(Finding(spec.name, "broken_transition_chain", aid))
        last_state = after
        if after != replay or a.get("independently_replayed") is not True:
            findings.append(Finding(spec.name, "state_replay_mismatch", aid))
        if _number(a.get("elapsed_ms"), "replay latency", high=1e12) > spec.threshold:
            findings.append(Finding(spec.name, "transition_latency_exceeded", aid))
    if len(attempts) < 3:
        findings.append(Finding(spec.name, "insufficient_recovery_replays", spec.name))
    return findings


_KERNELS = {
    "timing": _timing, "physics": _physics,
    "graph": _graph, "asset": _asset, "integrity": _integrity,
}


def audit_expanded_domain(spec: DomainSpec, evidence: Mapping, source_sha256: str) -> GateResult:
    """Run the typed bounded verifier for exactly one named owner contract."""
    if spec not in SPECS:
        raise QualityGateError("foreign production domain contract")
    source_sha256 = _sha(source_sha256, "full studio source")
    contract = _source(evidence, "expanded." + spec.name, source_sha256)
    findings = _KERNELS[spec.mode](spec, contract, source_sha256)
    return _result(spec.name, findings, contract)


def audit_expanded_studio(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Compose original 34 source gates plus 50 independently receipted domains."""
    base = audit_advanced_studio(bundle)
    studio = _source(bundle.get("studio"), "studio", base["source_digest"])
    expanded = _source(studio.get("expanded"), "studio.expanded", base["source_digest"])
    gates = list(base["gates"])
    findings = list(base["findings"])
    for spec in SPECS:
        domain = _source(expanded.get(spec.name), "studio.expanded." + spec.name, base["source_digest"])
        result = audit_expanded_domain(spec, domain, base["source_digest"])
        gates.append(result.as_dict())
        findings.extend(f.as_dict() for f in result.findings)
    return {
        "schema": "game.candidate.production_84.v1",
        "source_digest": base["source_digest"],
        "candidate_passed": not findings,
        "release_certified": False,
        "gates": gates,
        "findings": findings,
        "evidence_digest": _digest(gates),
    }


def verify_expanded_studio(bundle: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    """Independent full-source reconstruction; cannot accept a caller's green report."""
    expected = audit_expanded_studio(bundle)
    if not isinstance(report, Mapping) or dict(report) != expected:
        raise QualityGateError("84-gate source verifier rejected tampered or fabricated claim")
    result = {
        "schema": "game.studio.production_84_independent.v1",
        "source_sha256": expected["source_digest"],
        "evidence_sha256": expected["evidence_digest"],
        "gate_count": len(expected["gates"]),
        "candidate_passed": expected["candidate_passed"],
        "release_certified": False,
        "source_recomputed": True,
    }
    return {**result, "receipt_digest": _digest(result)}
