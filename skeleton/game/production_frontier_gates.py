"""Seven supplementary, source-bound original game production assurance gates.

Only caller-provided records are inspected. These gates NEVER invent generated
assets, model training, native frame capture, or legal rights. A candidate may
pass all checks and still be unqualified for production publication.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
from typing import Any

from .production_quality import Finding, GateResult, QualityGateError, _digest, _items, _record, _result
from .production_deep_gates import _id, _sha, audit_deep_candidate

_WORD = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_MAX = 4096


def _finite(value: Any, label: str, *, minimum: float = 0, maximum: float = 1e12) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise QualityGateError(f"{label} must be a finite bounded number")
    return float(value)


def audit_asset_lineage(lineage: Mapping[str, Any]) -> GateResult:
    """Every output is traceable to registered source inputs and a finite DAG."""
    lineage = _record(lineage, "lineage")
    source = _sha(lineage.get("source_sha256"), "lineage source")
    assets = _items(lineage.get("assets"), "lineage assets", _MAX)
    findings: list[Finding] = []
    graph: dict[str, tuple[str, ...]] = {}
    for asset in assets:
        asset = _record(asset, "lineage asset")
        ident = _id(asset.get("id"), "asset identity")
        if ident in graph:
            findings.append(Finding("lineage", "duplicate_asset", ident))
        deps = tuple(_id(x, "asset dependency") for x in _items(asset.get("inputs", []), "inputs", 256))
        graph[ident] = deps
        if asset.get("source_sha256") != source:
            findings.append(Finding("lineage", "foreign_source", ident))
        if asset.get("rights") not in ("homebrew", "licensed", "public_domain"):
            findings.append(Finding("lineage", "unresolved_rights", ident))
        if asset.get("kind") not in ("origin", "generated", "derived"):
            findings.append(Finding("lineage", "unknown_origin", ident))
        if asset.get("kind") != "origin" and not deps:
            findings.append(Finding("lineage", "orphan_derivative", ident))
        try:
            _sha(asset.get("sha256"), "asset bytes")
        except QualityGateError:
            findings.append(Finding("lineage", "unhashed_asset", ident))
    remaining = {key: len(set(d for d in deps if d in graph))
                 for key, deps in graph.items()}
    children: dict[str, set[str]] = {key: set() for key in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                findings.append(Finding("lineage", "missing_input", node + ":" + dep))
            else:
                children[dep].add(node)
    ready = deque(k for k, count in sorted(remaining.items()) if count == 0)
    while ready:
        node = ready.popleft()
        for child in sorted(children[node]):
            remaining[child] -= 1
            if remaining[child] == 0:
                ready.append(child)
    for node, count in sorted(remaining.items()):
        if count:
            findings.append(Finding("lineage", "source_cycle", node))
    if not assets:
        findings.append(Finding("lineage", "missing_assets", "lineage"))
    return _result("lineage", findings, lineage)


def audit_longform_continuity(timeline: Mapping[str, Any]) -> GateResult:
    """Follow canon character appearance and causal story promises across acts."""
    timeline = _record(timeline, "timeline")
    scenes = _items(timeline.get("scenes"), "timeline scenes", _MAX)
    cast = _items(timeline.get("cast"), "timeline cast", _MAX)
    findings: list[Finding] = []
    roster: dict[str, str] = {}
    for person in cast:
        person = _record(person, "character")
        ident = _id(person.get("id"), "character")
        appearance = person.get("appearance_sha256")
        if ident in roster:
            findings.append(Finding("continuity", "duplicate_character", ident))
        roster[ident] = _sha(appearance, "canonical appearance")
    promises: dict[str, str] = {}
    seen: set[str] = set()
    last_act, last_tick = 0, -1
    for scene in scenes:
        scene = _record(scene, "scene")
        sid = _id(scene.get("id"), "scene")
        if sid in seen:
            findings.append(Finding("continuity", "duplicate_scene", sid))
        seen.add(sid)
        act, tick = scene.get("act"), scene.get("tick")
        if type(act) is not int or not 1 <= act <= 10000:
            raise QualityGateError("act must be positive bounded integer")
        if type(tick) is not int or not 0 <= tick <= 10000000:
            raise QualityGateError("scene tick must be finite logical time")
        if act < last_act or (act == last_act and tick <= last_tick):
            findings.append(Finding("continuity", "nonmonotone_story", sid))
        last_act, last_tick = act, tick
        for actor in _items(scene.get("actors", []), "scene actors", 128):
            actor = _record(actor, "scene actor")
            ident = _id(actor.get("id"), "actor")
            if ident not in roster:
                findings.append(Finding("continuity", "unknown_character", sid + ":" + ident))
            elif actor.get("appearance_sha256") != roster[ident]:
                findings.append(Finding("continuity", "appearance_drift", sid + ":" + ident))
        for promise in _items(scene.get("introduces", []), "introduces", 128):
            promise = _id(promise, "promise")
            if promise in promises:
                findings.append(Finding("continuity", "reintroduced_promise", promise))
            else:
                promises[promise] = sid
        for payoff in _items(scene.get("resolves", []), "resolves", 128):
            payoff = _id(payoff, "payoff")
            if payoff not in promises:
                findings.append(Finding("continuity", "unearned_payoff", payoff))
            else:
                del promises[payoff]
    for promise in sorted(promises):
        findings.append(Finding("continuity", "unresolved_promise", promise))
    if not scenes:
        findings.append(Finding("continuity", "missing_scenes", "timeline"))
    return _result("continuity", findings, timeline)


def audit_route_coverage(routes: Mapping[str, Any]) -> GateResult:
    """Require at least one witnessed winning path per authored scenario."""
    routes = _record(routes, "routes")
    source = _sha(routes.get("source_sha256"), "route source")
    scenarios = _items(routes.get("scenarios"), "scenarios", 1024)
    observed = _items(routes.get("observations"), "observations", 8192)
    findings: list[Finding] = []
    defined = set()
    won: dict[str, set[str]] = {}
    for scenario in scenarios:
        scenario = _record(scenario, "scenario")
        sid = _id(scenario.get("id"), "scenario")
        if sid in defined:
            findings.append(Finding("routes", "duplicate_scenario", sid))
        defined.add(sid)
        min_alternatives = scenario.get("minimum_distinct_paths")
        if type(min_alternatives) is not int or not 1 <= min_alternatives <= 64:
            raise QualityGateError("finite scenario coverage target required")
    target = {s["id"]: s["minimum_distinct_paths"] for s in scenarios}
    for entry in observed:
        entry = _record(entry, "observed playthrough")
        sid = _id(entry.get("scenario"), "scenario")
        if sid not in defined:
            findings.append(Finding("routes", "unknown_scenario", sid))
            continue
        if entry.get("source_sha256") != source:
            findings.append(Finding("routes", "foreign_source", sid))
            continue
        steps = _items(entry.get("edge_ids"), "traversed edges", 65536)
        if not steps or any(type(x) is not str or not x or len(x) > 128 for x in steps):
            findings.append(Finding("routes", "invalid_path", sid))
            continue
        if entry.get("won") is not True or entry.get("independently_replayed") is not True:
            findings.append(Finding("routes", "unverified_outcome", sid))
            continue
        won.setdefault(sid, set()).add(_digest(steps))
    for sid in sorted(target):
        if len(won.get(sid, ())) < target[sid]:
            findings.append(Finding("routes", "insufficient_alternatives", sid))
    if not scenarios:
        findings.append(Finding("routes", "missing_scenarios", "routes"))
    return _result("routes", findings, routes)


def audit_physics_consistency(motion: Mapping[str, Any]) -> GateResult:
    """Bound telemetry deltas against supplied physical timestep and acceleration."""
    motion = _record(motion, "motion")
    _sha(motion.get("source_sha256"), "physics source")
    max_a = _finite(motion.get("max_acceleration"), "max acceleration", minimum=0.000001, maximum=100000)
    tolerance = _finite(motion.get("tolerance", 0.001), "physics tolerance", maximum=1)
    frames = _items(motion.get("frames"), "physics frames", 100000)
    findings: list[Finding] = []
    last: dict[str, tuple[float, tuple[float, ...], tuple[float, ...]]] = {}
    for index, frame in enumerate(frames):
        frame = _record(frame, "physics frame")
        actor = _id(frame.get("actor"), "physics actor")
        tick = _finite(frame.get("time_s"), "physics time", maximum=1e9)
        position = _items(frame.get("position"), "position", 3)
        velocity = _items(frame.get("velocity"), "velocity", 3)
        if len(position) != 3 or len(velocity) != 3:
            raise QualityGateError("3D scene position and velocity required")
        p = tuple(_finite(x, "position", minimum=-1e9, maximum=1e9) for x in position)
        v = tuple(_finite(x, "velocity", minimum=-1e6, maximum=1e6) for x in velocity)
        if actor in last:
            prior_time, prior_p, prior_v = last[actor]
            dt = tick - prior_time
            if dt <= 0 or dt > 3600:
                findings.append(Finding("physics", "invalid_timestep", actor + ":" + str(index)))
            else:
                acceleration = math.dist(v, prior_v) / dt
                residual = math.dist(p, tuple(prior_p[i] + (prior_v[i] + v[i]) * dt / 2 for i in range(3)))
                if acceleration > max_a + tolerance:
                    findings.append(Finding("physics", "excess_acceleration", actor + ":" + str(index)))
                if residual > tolerance + max_a * dt * dt:
                    findings.append(Finding("physics", "position_velocity_mismatch", actor + ":" + str(index)))
        last[actor] = tick, p, v
    if len(frames) < 2 or len(last) < 1:
        findings.append(Finding("physics", "insufficient_samples", "frames"))
    return _result("physics", findings, motion)


def audit_lod_fidelity(lod: Mapping[str, Any]) -> GateResult:
    """Require monotonic original mesh LOD budgets and stable observed transitions."""
    lod = _record(lod, "lod")
    meshes = _items(lod.get("meshes"), "LOD meshes", _MAX)
    samples = _items(lod.get("observations"), "LOD observations", 100000)
    findings: list[Finding] = []
    by_mesh: dict[str, dict[int, int]] = {}
    for record in meshes:
        record = _record(record, "mesh")
        mid = _id(record.get("mesh"), "mesh")
        level = record.get("level")
        tri = record.get("triangles")
        if type(level) is not int or not 0 <= level <= 7:
            raise QualityGateError("bounded LOD level required")
        if type(tri) is not int or not 1 <= tri <= 10_000_000:
            raise QualityGateError("finite triangle count required")
        try:
            _sha(record.get("sha256"), "LOD asset")
        except QualityGateError:
            findings.append(Finding("lod", "unhashed_mesh", mid))
        by_mesh.setdefault(mid, {})
        if level in by_mesh[mid]:
            findings.append(Finding("lod", "duplicate_lod", f"{mid}:{level}"))
        by_mesh[mid][level] = tri
    for mid, levels in sorted(by_mesh.items()):
        if 0 not in levels or len(levels) < 2:
            findings.append(Finding("lod", "missing_lod_levels", mid))
        for level in sorted(levels)[1:]:
            if levels[level] >= levels[min(x for x in levels if x < level)]:
                findings.append(Finding("lod", "nondecreasing_triangles", f"{mid}:{level}"))
    prior: dict[str, tuple[int, float, int]] = {}
    for index, row in enumerate(samples):
        row = _record(row, "LOD sample")
        mid = _id(row.get("mesh"), "LOD sample mesh")
        frame, level = row.get("frame"), row.get("level")
        distance = _finite(row.get("distance"), "LOD camera distance", maximum=1e8)
        if type(frame) is not int or frame < 0 or type(level) is not int:
            raise QualityGateError("LOD observation requires frame index and level")
        if mid not in by_mesh or level not in by_mesh[mid]:
            findings.append(Finding("lod", "unknown_mesh_level", f"{mid}:{level}"))
        if mid in prior:
            last_frame, last_distance, last_level = prior[mid]
            if frame <= last_frame:
                findings.append(Finding("lod", "nonmonotone_frame", mid))
            if abs(last_distance - distance) < 0.01 and level != last_level:
                findings.append(Finding("lod", "lod_flapping", mid + ":" + str(index)))
        prior[mid] = frame, distance, level
    if not samples:
        findings.append(Finding("lod", "no_runtime_observations", "lod"))
    if not meshes:
        findings.append(Finding("lod", "no_meshes", "lod"))
    return _result("lod", findings, lod)


def audit_localization(localization: Mapping[str, Any]) -> GateResult:
    """Require placeholder parity and translated captions for all declared keys."""
    localization = _record(localization, "localization")
    base = _record(localization.get("base"), "source strings")
    languages = _items(localization.get("languages"), "languages", 256)
    findings: list[Finding] = []
    if not base:
        findings.append(Finding("localization", "no_source_strings", "base"))
    for key, value in base.items():
        _id(key, "string key")
        if type(value) is not str or not value.strip() or len(value) > 10000:
            raise QualityGateError("bounded original string required")
    seen: set[str] = set()
    for lang in languages:
        lang = _record(lang, "locale")
        locale = _id(lang.get("id"), "locale")
        if locale in seen:
            findings.append(Finding("localization", "duplicate_locale", locale))
        seen.add(locale)
        translated = _record(lang.get("strings"), "translations")
        for key, source in base.items():
            text = translated.get(key)
            if type(text) is not str or not text.strip() or len(text) > 10000:
                findings.append(Finding("localization", "missing_string", f"{locale}:{key}"))
            elif set(_WORD.findall(text)) != set(_WORD.findall(source)):
                findings.append(Finding("localization", "placeholder_mismatch", f"{locale}:{key}"))
        for extra in sorted(set(translated) - set(base)):
            findings.append(Finding("localization", "unknown_string", f"{locale}:{extra}"))
    if not languages:
        findings.append(Finding("localization", "no_locales", "languages"))
    return _result("localization", findings, localization)


def audit_comparative_performance(perf: Mapping[str, Any]) -> GateResult:
    """Like-for-like objective comparison with noncompensable critical regressions."""
    perf = _record(perf, "comparative performance")
    baseline = _record(perf.get("baseline"), "baseline")
    candidate = _record(perf.get("candidate"), "candidate")
    findings: list[Finding] = []
    for label, data in (("baseline", baseline), ("candidate", candidate)):
        _sha(data.get("source_sha256"), label + " source")
        _sha(data.get("environment_sha256"), label + " environment")
        _sha(data.get("workload_sha256"), label + " workload")
    for pinned in ("environment_sha256", "workload_sha256"):
        if baseline[pinned] != candidate[pinned]:
            findings.append(Finding("comparison", "unfair_comparison", pinned))
    improved = False
    for metric in ("p50_ms", "p95_ms", "p99_ms", "ram_mb", "failure_count"):
        before = _finite(baseline.get(metric), "baseline " + metric)
        after = _finite(candidate.get(metric), "candidate " + metric)
        if after > before:
            findings.append(Finding("comparison", "regression", metric))
        elif after < before:
            improved = True
    if not improved:
        findings.append(Finding("comparison", "no_objective_improvement", "metrics"))
    for name in ("unauthorized_effects", "corrupted_saves", "copyright_violations"):
        if baseline.get(name) != 0 or candidate.get(name) != 0:
            findings.append(Finding("comparison", "critical_safety_failure", name))
    return _result("comparison", findings, perf)


FRONTIER_NAMES = (
    "lineage", "continuity", "routes", "physics",
    "lod", "localization", "comparison",
)


def audit_frontier_candidate(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Run all 20 candidate gates; never convert passed audits into signoff."""
    bundle = _record(bundle, "source candidate")
    original = audit_deep_candidate(bundle)
    frontier = _record(bundle.get("frontier"), "frontier")
    results = (
        audit_asset_lineage(frontier.get("lineage")),
        audit_longform_continuity(frontier.get("timeline")),
        audit_route_coverage(frontier.get("routes")),
        audit_physics_consistency(frontier.get("motion")),
        audit_lod_fidelity(frontier.get("lod")),
        audit_localization(frontier.get("localization")),
        audit_comparative_performance(frontier.get("comparison")),
    )
    gates = original["gates"] + [r.as_dict() for r in results]
    findings = original["findings"] + [f.as_dict() for r in results for f in r.findings]
    return {
        "schema": "game.candidate.frontier_quality.v1",
        "source_digest": original["source_digest"],
        "candidate_passed": not findings,
        "release_certified": False,
        "gates": gates, "findings": findings,
        "evidence_digest": _digest(gates),
    }


def verify_frontier_report(bundle: Mapping[str, Any], report: Mapping[str, Any]) -> dict:
    """Independently reproduce every gate and compare every reported finding."""
    expected = audit_frontier_candidate(bundle)
    if not isinstance(report, Mapping) or dict(report) != expected:
        raise QualityGateError("frontier verifier rejected altered acceptance report")
    result = {
        "schema": "game.frontier.independent_verify.v1",
        "source_digest": expected["source_digest"],
        "gate_count": len(expected["gates"]),
        "finding_count": len(expected["findings"]),
        "independent_replay_passed": True,
        "production_approval": False,
    }
    return {**result, "receipt_digest": _digest(result)}
