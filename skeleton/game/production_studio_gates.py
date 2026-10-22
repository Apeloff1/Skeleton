"""Seven original-game production verification planes above the canonical 20.

Scene direction, synchronized dialogue, NPC behavior, world streaming, durable
save upgrades, dynamic world hazards and controller latency are evaluated on
explicit source-pinned observations. Audits are candidate evidence, not
simulated native or physical-device attestation.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
import math
from typing import Any

from .production_quality import Finding, GateResult, QualityGateError, _digest, _items, _record, _result
from .production_deep_gates import _id, _sha
from .production_frontier_gates import audit_frontier_candidate


NAMES = ("cinematics", "dialogue_sync", "npc_behaviors", "streaming",
         "save_migrations", "dynamic_world", "input_latency")
_ALLOWED_FRAME_RATES = frozenset((24, 25, 30, 50, 60, 120, 144))


def _number(x: object, name: str, *, low: float = 0, high: float = 1e12) -> float:
    if type(x) not in (int, float) or not math.isfinite(x) or not low <= x <= high:
        raise QualityGateError(name + " must be a finite bounded number")
    return float(x)


def _positive_int(x: object, name: str, *, high: int = 1_000_000_000) -> int:
    if type(x) is not int or not 1 <= x <= high:
        raise QualityGateError(name + " must be a bounded positive integer")
    return x


def _source(obj: object, name: str, expected: str) -> Mapping:
    item = _record(obj, name)
    if _sha(item.get("source_sha256"), name + " source") != expected:
        raise QualityGateError(name + " foreign or unbound original game source")
    return item


def audit_cinematic_direction(data: Mapping[str, Any]) -> GateResult:
    """Require gap-free, ordered authored shots, safe camera envelopes and cuts."""
    data = _record(data, "cinematics")
    _sha(data.get("source_sha256"), "cinematics source")
    scenes = _items(data.get("scenes"), "cinematic scenes", 4096)
    findings: list[Finding] = []
    scene_ids: set[str] = set()
    for scene in scenes:
        scene = _record(scene, "cinematic scene")
        sid = _id(scene.get("id"), "cinematic id")
        if sid in scene_ids:
            findings.append(Finding("cinematics", "duplicate_scene", sid))
        scene_ids.add(sid)
        fps = scene.get("fps")
        if type(fps) is not int or fps not in _ALLOWED_FRAME_RATES:
            raise QualityGateError("cinematic requires supported integer FPS")
        duration = _positive_int(scene.get("total_frames"), "cinematic length")
        shots = _items(scene.get("shots"), "shots", 8192)
        expected_start = 0
        shot_ids: set[str] = set()
        for shot in shots:
            shot = _record(shot, "shot")
            ident = _id(shot.get("id"), "shot")
            if ident in shot_ids:
                findings.append(Finding("cinematics", "duplicate_shot", sid + ":" + ident))
            shot_ids.add(ident)
            begin, end = shot.get("start_frame"), shot.get("end_frame")
            if type(begin) is not int or type(end) is not int or not 0 <= begin < end <= duration:
                findings.append(Finding("cinematics", "invalid_time_span", sid + ":" + ident))
                continue
            if begin != expected_start:
                findings.append(Finding("cinematics", "timeline_gap_or_overlap", sid + ":" + ident))
            expected_start = end
            if type(shot.get("camera")) is not str or not shot["camera"].strip():
                findings.append(Finding("cinematics", "missing_camera", sid + ":" + ident))
            near = _number(shot.get("near_m"), "near clipping plane")
            far = _number(shot.get("far_m"), "far clipping plane")
            fov = _number(shot.get("fov_deg"), "camera field of view")
            if near <= 0 or far <= near or not 5 <= fov <= 170:
                findings.append(Finding("cinematics", "camera_envelope", sid + ":" + ident))
            if type(shot.get("intent")) is not str or not shot["intent"].strip():
                findings.append(Finding("cinematics", "undirected_shot", sid + ":" + ident))
        if not shots or expected_start != duration:
            findings.append(Finding("cinematics", "incomplete_timeline", sid))
    if not scenes:
        findings.append(Finding("cinematics", "missing_cinematics", "scenes"))
    return _result("cinematics", findings, data)


def audit_dialogue_sync(data: Mapping[str, Any]) -> GateResult:
    """Cross-check voice, subtitles and phoneme timing without inventing audio."""
    data = _record(data, "dialogue sync")
    _sha(data.get("source_sha256"), "dialogue source")
    cues = _items(data.get("cues"), "dialogue cues", 20000)
    tolerance = _number(data.get("tolerance_ms"), "dialogue sync tolerance", high=1000)
    findings: list[Finding] = []
    ids: set[str] = set()
    for cue in cues:
        cue = _record(cue, "cue")
        ident = _id(cue.get("id"), "cue")
        if ident in ids:
            findings.append(Finding("dialogue_sync", "duplicate_cue", ident))
        ids.add(ident)
        start = _number(cue.get("start_ms"), "voice start")
        end = _number(cue.get("end_ms"), "voice end")
        caption_start = _number(cue.get("caption_start_ms"), "caption start")
        caption_end = _number(cue.get("caption_end_ms"), "caption end")
        if end <= start or caption_end <= caption_start:
            findings.append(Finding("dialogue_sync", "invalid_cue_length", ident))
            continue
        if abs(start - caption_start) > tolerance or abs(end - caption_end) > tolerance:
            findings.append(Finding("dialogue_sync", "caption_drift", ident))
        if type(cue.get("caption")) is not str or not cue["caption"].strip():
            findings.append(Finding("dialogue_sync", "missing_caption", ident))
        if cue.get("has_voice") is not True:
            findings.append(Finding("dialogue_sync", "voice_unverified", ident))
        else:
            try:
                _sha(cue.get("voice_sha256"), "source voice")
            except QualityGateError:
                findings.append(Finding("dialogue_sync", "unhashed_voice", ident))
        phonemes = _items(cue.get("phonemes"), "phoneme observations", 4096)
        previous = start
        for phoneme in phonemes:
            p = _record(phoneme, "phoneme")
            onset = _number(p.get("time_ms"), "phoneme time")
            if onset < previous or onset > end:
                findings.append(Finding("dialogue_sync", "phoneme_out_of_order", ident))
            previous = onset
        if not phonemes:
            findings.append(Finding("dialogue_sync", "missing_lipsync_samples", ident))
    if not cues:
        findings.append(Finding("dialogue_sync", "missing_dialogue", "cues"))
    return _result("dialogue_sync", findings, data)


def audit_npc_behavior(data: Mapping[str, Any]) -> GateResult:
    """Reject unreachable NPC states, broken transitions and never-ending stalls."""
    data = _record(data, "npc behavior")
    _sha(data.get("source_sha256"), "NPC source")
    agents = _items(data.get("agents"), "agents", 4096)
    findings: list[Finding] = []
    all_ids: set[str] = set()
    for agent in agents:
        agent = _record(agent, "agent")
        aid = _id(agent.get("id"), "agent")
        if aid in all_ids:
            findings.append(Finding("npc_behaviors", "duplicate_npc", aid))
        all_ids.add(aid)
        states = _items(agent.get("states"), "NPC states", 4096)
        graph: dict[str, tuple[str, ...]] = {}
        terminals: set[str] = set()
        for state in states:
            state = _record(state, "NPC state")
            sid = _id(state.get("id"), "state")
            if sid in graph:
                findings.append(Finding("npc_behaviors", "duplicate_state", aid + ":" + sid))
            targets = tuple(_id(t, "NPC transition") for t in _items(state.get("next", []), "NPC transitions", 256))
            graph[sid] = targets
            if state.get("terminal") is True:
                terminals.add(sid)
            duration = _number(state.get("timeout_s"), "NPC state timeout", high=3600)
            if duration == 0 and sid not in terminals:
                findings.append(Finding("npc_behaviors", "unbounded_wait", aid + ":" + sid))
        initial = agent.get("spawn_state")
        if initial not in graph:
            findings.append(Finding("npc_behaviors", "missing_spawn", aid))
        for sid, targets in graph.items():
            if sid not in terminals and not targets:
                findings.append(Finding("npc_behaviors", "deadlock_state", aid + ":" + sid))
            for target in targets:
                if target not in graph:
                    findings.append(Finding("npc_behaviors", "unknown_transition", aid + ":" + sid))
        reachable: set[str] = set()
        todo = deque([initial]) if initial in graph else deque()
        while todo:
            node = todo.popleft()
            if node in reachable:
                continue
            reachable.add(node)
            todo.extend(t for t in graph[node] if t in graph and t not in reachable)
        reverse: dict[str, set[str]] = {s: set() for s in graph}
        for sid, targets in graph.items():
            for target in targets:
                if target in reverse:
                    reverse[target].add(sid)
        can_finish = set(terminals)
        todo = deque(sorted(terminals))
        while todo:
            node = todo.popleft()
            for previous in reverse[node]:
                if previous not in can_finish:
                    can_finish.add(previous)
                    todo.append(previous)
        for sid in sorted(set(graph) - reachable):
            findings.append(Finding("npc_behaviors", "unreachable_state", aid + ":" + sid))
        for sid in sorted(reachable - can_finish):
            findings.append(Finding("npc_behaviors", "no_terminal_path", aid + ":" + sid))
        if not states:
            findings.append(Finding("npc_behaviors", "empty_behavior", aid))
    if not agents:
        findings.append(Finding("npc_behaviors", "missing_agents", "agents"))
    return _result("npc_behaviors", findings, data)


def audit_world_streaming(data: Mapping[str, Any]) -> GateResult:
    """Simulate neighborhood residency with dependency closure and RAM budgets."""
    data = _record(data, "streaming")
    _sha(data.get("source_sha256"), "streaming source")
    max_chunk = _positive_int(data.get("max_chunk_bytes"), "single chunk byte ceiling")
    max_resident = _positive_int(data.get("max_resident_bytes"), "resident bytes ceiling")
    chunks = _items(data.get("chunks"), "world chunks", 4096)
    findings: list[Finding] = []
    size: dict[str, int] = {}
    neighbors: dict[str, tuple[str, ...]] = {}
    requires: dict[str, tuple[str, ...]] = {}
    for chunk in chunks:
        chunk = _record(chunk, "chunk")
        ident = _id(chunk.get("id"), "world chunk")
        if ident in size:
            findings.append(Finding("streaming", "duplicate_chunk", ident))
        bytes_used = _positive_int(chunk.get("bytes"), "chunk bytes", high=1_000_000_000)
        size[ident] = bytes_used
        if bytes_used > max_chunk:
            findings.append(Finding("streaming", "oversize_chunk", ident))
        try:
            _sha(chunk.get("sha256"), "chunk source")
        except QualityGateError:
            findings.append(Finding("streaming", "missing_chunk_digest", ident))
        neighbors[ident] = tuple(_id(x, "neighbor") for x in _items(chunk.get("neighbors", []), "neighbors", 256))
        requires[ident] = tuple(_id(x, "dependency") for x in _items(chunk.get("requires", []), "requires", 256))
    start = data.get("entry_chunk")
    if start not in size:
        findings.append(Finding("streaming", "missing_entry", str(start)))
    seen: set[str] = set()
    pending = deque([start]) if start in size else deque()
    while pending:
        node = pending.popleft()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(n for n in neighbors[node] if n in size and n not in seen)
    for ident in sorted(size):
        for next_id in neighbors[ident]:
            if next_id not in size:
                findings.append(Finding("streaming", "missing_neighbor", ident + ":" + next_id))
        for needed in requires[ident]:
            if needed not in size:
                findings.append(Finding("streaming", "missing_dependency", ident + ":" + needed))
        if ident not in seen:
            findings.append(Finding("streaming", "unreachable_chunk", ident))
        resident = set([ident]) | set(neighbors[ident])
        todo = list(resident)
        while todo:
            cur = todo.pop()
            for dep in requires.get(cur, ()):
                if dep in size and dep not in resident:
                    resident.add(dep)
                    todo.append(dep)
        used = sum(size.get(x, 0) for x in resident)
        if used > max_resident:
            findings.append(Finding("streaming", "resident_budget_exceeded", ident))
    if not chunks:
        findings.append(Finding("streaming", "missing_chunks", "chunks"))
    return _result("streaming", findings, data)


def audit_save_evolution(data: Mapping[str, Any]) -> GateResult:
    """Check migration chains and separately replayed state transformations."""
    data = _record(data, "save evolution")
    _sha(data.get("source_sha256"), "save schema source")
    current = _positive_int(data.get("current_version"), "current save version", high=1024)
    supported = _items(data.get("supported_versions"), "supported saves", 1024)
    migrations = _items(data.get("migrations"), "migrations", 1024)
    findings: list[Finding] = []
    routes: dict[int, int] = {}
    transition_proofs: dict[int, tuple[str, str]] = {}
    for migration in migrations:
        migration = _record(migration, "migration")
        start, end = migration.get("from_version"), migration.get("to_version")
        if (type(start) is not int or type(end) is not int or
                not 1 <= start < end <= current):
            findings.append(Finding("save_migrations", "invalid_version_step", str(start)))
            continue
        if start in routes:
            findings.append(Finding("save_migrations", "ambiguous_migration", str(start)))
        routes[start] = end
        if (type(migration.get("input_sha256")) is str and
                type(migration.get("output_sha256")) is str):
            transition_proofs[start] = (
                migration["input_sha256"], migration["output_sha256"]
            )
        try:
            _sha(migration.get("transform_sha256"), "migration transform")
            _sha(migration.get("input_sha256"), "migration input")
            _sha(migration.get("output_sha256"), "migration output")
        except QualityGateError:
            findings.append(Finding("save_migrations", "missing_migration_digest", str(start)))
        if migration.get("independently_replayed") is not True:
            findings.append(Finding("save_migrations", "unverified_transform", str(start)))
    for start, end in sorted(routes.items()):
        if end in transition_proofs and start in transition_proofs and (
                transition_proofs[start][1] != transition_proofs[end][0]):
            findings.append(Finding("save_migrations", "unlinked_migration_bytes", str(start)))
    if len(set(supported)) != len(supported):
        findings.append(Finding("save_migrations", "duplicate_supported_version", "supported_versions"))
    for version in supported:
        if type(version) is not int or not 1 <= version <= current:
            raise QualityGateError("supported save version out of bounds")
        node = version
        visited = set()
        while node != current and node in routes and node not in visited:
            visited.add(node)
            node = routes[node]
        if node != current:
            findings.append(Finding("save_migrations", "unsupported_upgrade", str(version)))
    if not supported or current not in supported:
        findings.append(Finding("save_migrations", "current_version_not_supported", str(current)))
    return _result("save_migrations", findings, data)


def audit_dynamic_world(data: Mapping[str, Any]) -> GateResult:
    """Require original weather/hazard transitions and observed playable states."""
    data = _record(data, "dynamic world")
    _sha(data.get("source_sha256"), "dynamic world source")
    states = _items(data.get("states"), "world states", 512)
    traces = _items(data.get("observations"), "environment replay", 4096)
    findings: list[Finding] = []
    by_id: dict[str, Mapping] = {}
    for state in states:
        state = _record(state, "environment state")
        ident = _id(state.get("id"), "weather/hazard state")
        if ident in by_id:
            findings.append(Finding("dynamic_world", "duplicate_state", ident))
        by_id[ident] = state
        _sha(state.get("effect_sha256"), "weather effect source")
        if type(state.get("hazardous")) is not bool:
            raise QualityGateError("dynamic hazard designation must be explicit boolean")
        if state["hazardous"]:
            mitigation = state.get("mitigation", [])
            if type(mitigation) not in (tuple, list):
                raise QualityGateError("hazard mitigation must be bounded source action list")
            if not mitigation or len(mitigation) > 128 or any(
                    type(token) is not str or not token.strip() or len(token) > 128
                    for token in mitigation):
                findings.append(Finding("dynamic_world", "unmitigated_hazard", ident))
    for sid, state in by_id.items():
        transitions = _items(state.get("transitions"), "weather transitions", 256)
        if not transitions:
            findings.append(Finding("dynamic_world", "stalled_environment", sid))
        total = 0.0
        for edge in transitions:
            edge = _record(edge, "environment transition")
            target = _id(edge.get("to"), "weather target")
            if target not in by_id:
                findings.append(Finding("dynamic_world", "foreign_environment", sid + ":" + target))
            total += _number(edge.get("probability"), "weather probability", high=1)
        if abs(total - 1) > 1e-6:
            findings.append(Finding("dynamic_world", "invalid_transition_weights", sid))
    covered = set()
    for trace in traces:
        trace = _record(trace, "weather observed trace")
        state = _id(trace.get("state"), "weather trace state")
        if state not in by_id:
            findings.append(Finding("dynamic_world", "unknown_observed_weather", state))
            continue
        if trace.get("independently_replayed") is not True:
            findings.append(Finding("dynamic_world", "unverified_world_effect", state))
            continue
        if trace.get("effect_sha256") != by_id[state]["effect_sha256"]:
            findings.append(Finding("dynamic_world", "effect_divergence", state))
            continue
        covered.add(state)
    for state in sorted(set(by_id) - covered):
        findings.append(Finding("dynamic_world", "unobserved_weather", state))
    if not states:
        findings.append(Finding("dynamic_world", "missing_environment_states", "states"))
    return _result("dynamic_world", findings, data)


def audit_controller_latency(data: Mapping[str, Any]) -> GateResult:
    """Measure input-response tails; observed timestamps are not device attestation."""
    data = _record(data, "controller latency")
    _sha(data.get("source_sha256"), "input source")
    limit95 = _number(data.get("max_p95_ms"), "p95 budget", low=0.01, high=1000)
    limit99 = _number(data.get("max_p99_ms"), "p99 budget", low=0.01, high=2000)
    if limit99 < limit95:
        raise QualityGateError("p99 response budget cannot be stricter than p95 budget")
    frames = _items(data.get("observations"), "latency observations", 100000)
    findings: list[Finding] = []
    per_device: dict[str, list[float]] = {}
    previous: dict[str, float] = {}
    for index, record in enumerate(frames):
        record = _record(record, "latency observation")
        device = _id(record.get("device"), "controller device")
        start = _number(record.get("input_ms"), "input timestamp")
        end = _number(record.get("render_ack_ms"), "observed response")
        if end < start:
            findings.append(Finding("input_latency", "reversed_observation_clock", str(index)))
            continue
        if device in previous and start < previous[device]:
            findings.append(Finding("input_latency", "nonmonotone_input", device))
        previous[device] = start
        per_device.setdefault(device, []).append(end - start)
        if record.get("source_sha256") != data["source_sha256"]:
            findings.append(Finding("input_latency", "foreign_input_source", str(index)))
        if record.get("observed") is not True:
            findings.append(Finding("input_latency", "unverified_response", str(index)))
    for device in ("keyboard", "gamepad"):
        if device not in per_device:
            findings.append(Finding("input_latency", "missing_device", device))
    for device, delays in sorted(per_device.items()):
        if len(delays) < 10:
            findings.append(Finding("input_latency", "insufficient_samples", device))
            continue
        delays.sort()
        def percentile(p: int) -> float:
            return delays[math.ceil(p / 100 * len(delays)) - 1]
        if percentile(95) > limit95:
            findings.append(Finding("input_latency", "p95_exceeded", device))
        if percentile(99) > limit99:
            findings.append(Finding("input_latency", "p99_exceeded", device))
    return _result("input_latency", findings, data)


def audit_complete_studio(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Compose 20 existing and 7 concrete production domains into 27 gates."""
    bundle = _record(bundle, "studio source")
    original = audit_frontier_candidate(bundle)
    studio = _source(bundle.get("studio"), "studio", original["source_digest"])
    subcontracts = ("cinematics", "dialogue", "npcs", "streaming",
                    "saves", "environment", "latency")
    for key in subcontracts:
        _source(studio.get(key), "studio." + key, original["source_digest"])
    audits = (
        audit_cinematic_direction(studio["cinematics"]),
        audit_dialogue_sync(studio["dialogue"]),
        audit_npc_behavior(studio["npcs"]),
        audit_world_streaming(studio["streaming"]),
        audit_save_evolution(studio["saves"]),
        audit_dynamic_world(studio["environment"]),
        audit_controller_latency(studio["latency"]),
    )
    gates = original["gates"] + [g.as_dict() for g in audits]
    findings = original["findings"] + [f.as_dict() for g in audits for f in g.findings]
    return {
        "schema": "game.candidate.complete_studio.v1",
        "source_digest": original["source_digest"],
        "candidate_passed": not findings,
        "release_certified": False,
        "gates": gates,
        "findings": findings,
        "evidence_digest": _digest(gates),
    }


def verify_complete_studio(bundle: Mapping[str, Any], report: Mapping[str, Any]) -> dict:
    """Second independently reconstructed 27-gate source evidence evaluation."""
    expected = audit_complete_studio(bundle)
    if not isinstance(report, Mapping) or dict(report) != expected:
        raise QualityGateError("independent studio reviewer rejected fabricated evidence")
    result = {
        "schema": "game.studio.independent_review.v1",
        "source_digest": expected["source_digest"],
        "gate_count": len(expected["gates"]),
        "candidate_passed": expected["candidate_passed"],
        "release_certified": False,
        "source_recomputation": True,
    }
    return {**result, "receipt_digest": _digest(result)}
