"""Seven source-bound advanced original-game audit domains (28-34).

These validators audit *declared candidate evidence*; they do not manufacture
native, device, multiplayer, rights, privacy or release certification. All
collection sizes, numeric parameters and identifiers are bounded.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from .production_quality import Finding, GateResult, QualityGateError, _digest, _items, _record, _result
from .production_deep_gates import _id, _sha
from .production_studio_gates import _number, _positive_int, _source, audit_complete_studio

NAMES = (
    "audio_mix", "procedural_replay", "economy_integrity",
    "multiplayer_sync", "transport_paths", "privacy_consent",
    "endurance_recovery",
)
CONTRACTS = ("audio", "procedural", "economy", "multiplayer", "transport", "privacy", "endurance")
MODES = frozenset((
    "foot", "road", "rail", "water", "air", "space", "magic",
    "teleport", "underground",
))


def audit_audio_mix(data: Mapping[str, Any]) -> GateResult:
    """Audit source-pinned buses, dynamic music transitions and peak headroom."""
    data = _record(data, "audio")
    source = _sha(data.get("source_sha256"), "audio source")
    buses = _items(data.get("buses"), "audio buses", 128)
    cues = _items(data.get("cues"), "music cues", 4096)
    observations = _items(data.get("observations"), "audio observations", 50000)
    findings: list[Finding] = []
    names: set[str] = set()
    for bus in buses:
        b = _record(bus, "audio bus")
        name = _id(b.get("id"), "audio bus id")
        if name in names:
            findings.append(Finding("audio_mix", "duplicate_bus", name))
        names.add(name)
        gain = _number(b.get("gain_db"), "audio bus gain", low=-96, high=24)
        if gain > 6:
            findings.append(Finding("audio_mix", "amplified_bus", name))
        if b.get("limiter") is not True:
            findings.append(Finding("audio_mix", "unlimited_bus", name))
    cue_ids: set[str] = set()
    edges: dict[str, list[str]] = {}
    for cue in cues:
        c = _record(cue, "audio cue")
        cid = _id(c.get("id"), "audio cue id")
        if cid in cue_ids:
            findings.append(Finding("audio_mix", "duplicate_cue", cid))
        cue_ids.add(cid)
        _sha(c.get("asset_sha256"), "audio asset")
        if c.get("bus") not in names:
            findings.append(Finding("audio_mix", "missing_bus", cid))
        targets = _items(c.get("transitions"), "audio transitions", 64)
        edges[cid] = [_id(t, "cue transition") for t in targets]
    for key, destinations in edges.items():
        for dest in destinations:
            if dest not in cue_ids:
                findings.append(Finding("audio_mix", "unknown_transition", key + ":" + dest))
    observed: set[str] = set()
    for obs in observations:
        o = _record(obs, "audio sample")
        cid = _id(o.get("cue"), "observed audio cue")
        observed.add(cid)
        if o.get("source_sha256") != source:
            findings.append(Finding("audio_mix", "foreign_source", cid))
        _sha(o.get("capture_sha256"), "mix capture")
        true_peak = _number(o.get("true_peak_dbfs"), "true peak", low=-120, high=24)
        _number(o.get("integrated_lufs"), "integrated loudness", low=-100, high=20)
        if true_peak > -1:
            findings.append(Finding("audio_mix", "clipping_risk", cid))
        if o.get("measured") is not True:
            findings.append(Finding("audio_mix", "unmeasured_audio", cid))
        if cid not in cue_ids:
            findings.append(Finding("audio_mix", "unknown_observed_cue", cid))
    for cid in sorted(cue_ids - observed):
        findings.append(Finding("audio_mix", "missing_mix_observation", cid))
    if not buses or not cues:
        findings.append(Finding("audio_mix", "missing_soundscape", "audio"))
    return _result("audio_mix", findings, data)


def audit_procedural_replay(data: Mapping[str, Any]) -> GateResult:
    """Require paired independently replayed seed digests and canonical uniqueness."""
    data = _record(data, "procedural")
    source = _sha(data.get("source_sha256"), "procedural source")
    generators = _items(data.get("generators"), "procedural generators", 4096)
    findings: list[Finding] = []
    ids: set[str] = set()
    outputs: set[tuple[str, str]] = set()
    for generator in generators:
        g = _record(generator, "procedural generator")
        gid = _id(g.get("id"), "procedural generator id")
        if gid in ids:
            findings.append(Finding("procedural_replay", "duplicate_generator", gid))
        ids.add(gid)
        _sha(g.get("algorithm_sha256"), "procedural algorithm")
        seeds = _items(g.get("seeds"), "procedural seeds", 4096)
        distinct: set[int] = set()
        for sample in seeds:
            s = _record(sample, "procedural seed")
            seed = s.get("seed")
            if type(seed) is not int or not 0 <= seed <= 2**64 - 1:
                raise QualityGateError("procedural seed must be uint64")
            if seed in distinct:
                findings.append(Finding("procedural_replay", "duplicate_seed", gid))
            distinct.add(seed)
            left = _sha(s.get("first_sha256"), "initial procedural output")
            right = _sha(s.get("replay_sha256"), "replayed procedural output")
            _sha(s.get("replay_engine_sha256"), "independent replay engine")
            if s.get("source_sha256") != source:
                findings.append(Finding("procedural_replay", "foreign_source", gid))
            if left != right or s.get("independent") is not True:
                findings.append(Finding("procedural_replay", "nondeterministic_seed", gid + ":" + str(seed)))
            if (gid, left) in outputs and s.get("allow_equivalent") is not True:
                findings.append(Finding("procedural_replay", "collapsed_variation", gid + ":" + str(seed)))
            outputs.add((gid, left))
        if len(distinct) < 2:
            findings.append(Finding("procedural_replay", "insufficient_seed_coverage", gid))
    if not generators:
        findings.append(Finding("procedural_replay", "missing_generators", "procedural"))
    return _result("procedural_replay", findings, data)


def audit_economy_integrity(data: Mapping[str, Any]) -> GateResult:
    """Conserve bounded ledger units and reject free crafting/currency loops."""
    data = _record(data, "economy")
    _sha(data.get("source_sha256"), "economy source")
    currencies = _items(data.get("currencies"), "economy currencies", 64)
    transactions = _items(data.get("transactions"), "economy transactions", 20000)
    recipes = _items(data.get("recipes"), "crafting recipes", 10000)
    findings: list[Finding] = []
    symbols = {_id(x, "currency") for x in currencies}
    if len(symbols) != len(currencies) or not symbols:
        findings.append(Finding("economy_integrity", "missing_or_duplicate_currency", "currency"))
    txids: set[str] = set()
    for tx in transactions:
        t = _record(tx, "ledger transaction")
        tid = _id(t.get("id"), "ledger transaction id")
        if tid in txids:
            findings.append(Finding("economy_integrity", "duplicate_transaction", tid))
        txids.add(tid)
        entries = _items(t.get("entries"), "ledger postings", 128)
        totals = {currency: 0 for currency in symbols}
        for entry in entries:
            e = _record(entry, "ledger entry")
            currency = _id(e.get("currency"), "posting currency")
            _id(e.get("account"), "ledger account")
            amount = e.get("amount")
            if type(amount) is not int or abs(amount) > 10**12:
                raise QualityGateError("ledger posting requires bounded integer minimal units")
            if currency not in totals:
                findings.append(Finding("economy_integrity", "unknown_currency", tid))
                continue
            totals[currency] += amount
        if len(entries) < 2 or any(totals.values()):
            findings.append(Finding("economy_integrity", "unbalanced_transaction", tid))
        if t.get("replayed") is not True:
            findings.append(Finding("economy_integrity", "unreplayed_transaction", tid))
    recipe_ids: set[str] = set()
    recipe_graph: dict[str, set[str]] = {}
    for recipe in recipes:
        r = _record(recipe, "craft recipe")
        rid = _id(r.get("id"), "craft recipe id")
        if rid in recipe_ids:
            findings.append(Finding("economy_integrity", "duplicate_recipe", rid))
        recipe_ids.add(rid)
        ingredients = _items(r.get("ingredients"), "craft ingredients", 100)
        if not ingredients:
            findings.append(Finding("economy_integrity", "free_output", rid))
        for ingredient in ingredients:
            i = _record(ingredient, "recipe ingredient")
            _id(i.get("item"), "ingredient")
            _positive_int(i.get("quantity"), "ingredient count", high=1_000_000)
        _id(r.get("output"), "craft output")
        _positive_int(r.get("output_quantity"), "craft output count", high=1_000_000)
        recipe_graph[rid] = {_id(x, "craft dependency") for x in _items(r.get("requires_recipes"), "recipe dependencies", 100)}
    for rid, deps in recipe_graph.items():
        if deps - recipe_ids:
            findings.append(Finding("economy_integrity", "unknown_recipe_dependency", rid))
    visiting: set[str] = set()
    visited: set[str] = set()
    # Iterative check prevents Python recursion failure on adversarially deep graphs.
    for rid in sorted(recipe_ids):
        stack = [(rid, False)]
        active: set[str] = set()
        while stack:
            node, leave = stack.pop()
            if leave:
                active.discard(node)
                visited.add(node)
            elif node in active:
                findings.append(Finding("economy_integrity", "craft_dependency_cycle", node))
            elif node not in visited:
                active.add(node)
                stack.append((node, True))
                stack.extend((dep, False) for dep in sorted(recipe_graph[node] & recipe_ids, reverse=True))
    if not transactions:
        findings.append(Finding("economy_integrity", "missing_ledger_replay", "transactions"))
    return _result("economy_integrity", findings, data)


def audit_multiplayer_sync(data: Mapping[str, Any]) -> GateResult:
    """Audit per-tick authoritative digest agreement, replay receipts and lag."""
    data = _record(data, "multiplayer")
    source = _sha(data.get("source_sha256"), "multiplayer source")
    peers = _items(data.get("peers"), "session peers", 64)
    frames = _items(data.get("frames"), "network frames", 100000)
    tolerance = _number(data.get("max_divergence_ms"), "network lag budget", high=5000)
    findings: list[Finding] = []
    peer_ids = {_id(x, "peer") for x in peers}
    if len(peer_ids) < 2 or len(peer_ids) != len(peers):
        findings.append(Finding("multiplayer_sync", "missing_or_duplicate_peers", "peers"))
    observed: dict[tuple[int, str], str] = {}
    previous: dict[str, int] = {}
    ticks: dict[int, dict[str, str]] = {}
    for frame in frames:
        f = _record(frame, "network frame")
        peer = _id(f.get("peer"), "network peer")
        tick = _positive_int(f.get("tick"), "network tick", high=10**9)
        digest = _sha(f.get("state_sha256"), "network state")
        _sha(f.get("input_sha256"), "network input")
        _sha(f.get("replay_sha256"), "network replay receipt")
        if f.get("source_sha256") != source or f.get("replayed") is not True:
            findings.append(Finding("multiplayer_sync", "unverified_frame", peer + ":" + str(tick)))
        if peer not in peer_ids:
            findings.append(Finding("multiplayer_sync", "unknown_peer", peer))
        if tick <= previous.get(peer, 0):
            findings.append(Finding("multiplayer_sync", "nonmonotone_tick", peer))
        previous[peer] = tick
        key = (tick, peer)
        if key in observed:
            findings.append(Finding("multiplayer_sync", "duplicate_peer_tick", peer + ":" + str(tick)))
        observed[key] = digest
        ticks.setdefault(tick, {})[peer] = digest
        if _number(f.get("lag_ms"), "per-peer lag", high=100000) > tolerance:
            findings.append(Finding("multiplayer_sync", "lag_budget_exceeded", peer + ":" + str(tick)))
    for tick, states in ticks.items():
        if set(states) != peer_ids:
            findings.append(Finding("multiplayer_sync", "missing_tick_ack", str(tick)))
        if len(set(states.values())) != 1:
            findings.append(Finding("multiplayer_sync", "state_divergence", str(tick)))
    if len(ticks) < 3:
        findings.append(Finding("multiplayer_sync", "insufficient_replay", "ticks"))
    return _result("multiplayer_sync", findings, data)


def audit_transport_paths(data: Mapping[str, Any]) -> GateResult:
    """Verify multi-modal route graph, terminals and fallback access after hazards."""
    data = _record(data, "transport")
    _sha(data.get("source_sha256"), "transport source")
    nodes = _items(data.get("nodes"), "transport nodes", 20000)
    links = _items(data.get("links"), "transport links", 100000)
    findings: list[Finding] = []
    node_ids = {_id(n, "transport node") for n in nodes}
    if len(node_ids) != len(nodes):
        findings.append(Finding("transport_paths", "duplicate_waypoint", "nodes"))
    origin = _id(data.get("origin"), "transport origin")
    destinations = {_id(x, "transport destination") for x in _items(data.get("destinations"), "transport destinations", 256)}
    if origin not in node_ids or not destinations or not destinations <= node_ids:
        findings.append(Finding("transport_paths", "missing_terminal", origin))
    graph: dict[str, set[str]] = {key: set() for key in node_ids}
    link_ids: set[str] = set()
    covered_modes: set[str] = set()
    for link in links:
        l = _record(link, "transport link")
        lid = _id(l.get("id"), "transport link id")
        if lid in link_ids:
            findings.append(Finding("transport_paths", "duplicate_route", lid))
        link_ids.add(lid)
        a, b = _id(l.get("from"), "transport link source"), _id(l.get("to"), "transport link target")
        mode = _id(l.get("mode"), "transport mode")
        if mode not in MODES:
            findings.append(Finding("transport_paths", "unknown_mode", lid))
        covered_modes.add(mode)
        cost = _number(l.get("duration_s"), "route duration", high=10**7)
        if cost <= 0:
            findings.append(Finding("transport_paths", "zero_cost_route", lid))
        if l.get("hazardous") is True and (l.get("mitigated") is not True or
                l.get("fallback") is not True):
            findings.append(Finding("transport_paths", "hazard_no_fallback", lid))
        if a not in graph or b not in graph:
            findings.append(Finding("transport_paths", "dangling_route", lid))
        else:
            graph[a].add(b)
            if l.get("bidirectional") is True:
                graph[b].add(a)
    seen = {origin}
    queue = deque([origin])
    while queue:
        at = queue.popleft()
        for nxt in graph.get(at, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    for lost in sorted(destinations - seen):
        findings.append(Finding("transport_paths", "unreachable_destination", lost))
    if len(covered_modes & MODES) < 2:
        findings.append(Finding("transport_paths", "single_mode_world", "transport"))
    return _result("transport_paths", findings, data)


def audit_privacy_consent(data: Mapping[str, Any]) -> GateResult:
    """Audit declared consent-to-event routing and opt-out replay without raw PII."""
    data = _record(data, "privacy")
    source = _sha(data.get("source_sha256"), "privacy source")
    purposes = _items(data.get("purposes"), "telemetry purposes", 64)
    observations = _items(data.get("observations"), "telemetry observations", 20000)
    findings: list[Finding] = []
    ids: set[str] = set()
    for p in purposes:
        item = _record(p, "consent purpose")
        pid = _id(item.get("id"), "consent purpose id")
        if pid in ids:
            findings.append(Finding("privacy_consent", "duplicate_purpose", pid))
        ids.add(pid)
        ttl = _positive_int(item.get("retention_hours"), "data retention hours", high=87600)
        if ttl > 720:
            findings.append(Finding("privacy_consent", "excess_retention", pid))
        if item.get("opt_in_default") is not False:
            findings.append(Finding("privacy_consent", "nonconsensual_default", pid))
        if item.get("personal_data") is not False:
            findings.append(Finding("privacy_consent", "personal_data_unreviewed", pid))
    observed_disabled: set[str] = set()
    for obs in observations:
        o = _record(obs, "consent observation")
        pid = _id(o.get("purpose"), "telemetry purpose")
        if pid not in ids:
            findings.append(Finding("privacy_consent", "unknown_purpose", pid))
        if o.get("source_sha256") != source:
            findings.append(Finding("privacy_consent", "foreign_observation", pid))
        _sha(o.get("event_schema_sha256"), "telemetry event schema")
        if o.get("consent") is False:
            observed_disabled.add(pid)
            if o.get("emitted") is not False:
                findings.append(Finding("privacy_consent", "opt_out_leak", pid))
        elif o.get("consent") is True:
            if o.get("emitted") is not True:
                findings.append(Finding("privacy_consent", "consent_trace_missing", pid))
        else:
            findings.append(Finding("privacy_consent", "untyped_consent", pid))
        if o.get("contains_raw_identifier") is not False:
            findings.append(Finding("privacy_consent", "raw_identifier", pid))
        if o.get("independently_replayed") is not True:
            findings.append(Finding("privacy_consent", "unreplayed_consent", pid))
    for pid in sorted(ids - observed_disabled):
        findings.append(Finding("privacy_consent", "missing_opt_out_probe", pid))
    if not ids:
        findings.append(Finding("privacy_consent", "missing_consent_policies", "purposes"))
    return _result("privacy_consent", findings, data)


def audit_endurance_recovery(data: Mapping[str, Any]) -> GateResult:
    """Check source-bound long-run samples, resource ceilings and restart replay."""
    data = _record(data, "endurance")
    source = _sha(data.get("source_sha256"), "endurance source")
    max_mem = _positive_int(data.get("max_memory_mb"), "memory ceiling", high=10**6)
    max_frame = _number(data.get("max_p99_frame_ms"), "p99 frame ceiling", high=10000)
    max_recovery = _number(data.get("max_recovery_ms"), "recovery time budget", high=10**9)
    readings = _items(data.get("samples"), "endurance samples", 100000)
    restores = _items(data.get("restores"), "restart observations", 10000)
    findings: list[Finding] = []
    previous = -1.0
    first = None
    for reading in readings:
        r = _record(reading, "endurance observation")
        at = _number(r.get("elapsed_s"), "endurance elapsed time", high=10**9)
        mem = _positive_int(r.get("resident_mb"), "resident memory", high=10**6)
        frame = _number(r.get("p99_frame_ms"), "sample tail frame", high=10000)
        if at <= previous:
            findings.append(Finding("endurance_recovery", "nonmonotone_sample", str(at)))
        previous = at
        if first is None:
            first = at
        if mem > max_mem or frame > max_frame:
            findings.append(Finding("endurance_recovery", "resource_budget_exceeded", str(at)))
        if r.get("source_sha256") != source or r.get("observed") is not True:
            findings.append(Finding("endurance_recovery", "unverified_sample", str(at)))
        _sha(r.get("telemetry_sha256"), "endurance telemetry")
    if len(readings) < 3 or first is None or previous - first < 86400:
        findings.append(Finding("endurance_recovery", "insufficient_24h_coverage", "samples"))
    if not restores:
        findings.append(Finding("endurance_recovery", "missing_restore_replay", "restores"))
    for n, restore in enumerate(restores):
        r = _record(restore, "restart replay")
        before = _sha(r.get("before_sha256"), "checkpoint state")
        after = _sha(r.get("after_sha256"), "restored state")
        _sha(r.get("capture_sha256"), "restore capture")
        delay = _number(r.get("recovery_ms"), "restart delay", high=10**9)
        if before != after or delay > max_recovery or r.get("replayed") is not True:
            findings.append(Finding("endurance_recovery", "failed_stateful_restore", str(n)))
        if r.get("source_sha256") != source:
            findings.append(Finding("endurance_recovery", "foreign_restore", str(n)))
    return _result("endurance_recovery", findings, data)


AUDITORS = (
    audit_audio_mix, audit_procedural_replay, audit_economy_integrity,
    audit_multiplayer_sync, audit_transport_paths, audit_privacy_consent,
    audit_endurance_recovery,
)


def audit_advanced_studio(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Compose existing 27 evidence gates plus seven original advanced planes."""
    base = audit_complete_studio(bundle)
    studio = _source(bundle.get("studio"), "studio", base["source_digest"])
    advanced = _source(studio.get("advanced"), "studio.advanced", base["source_digest"])
    gates = list(base["gates"])
    findings = list(base["findings"])
    for key, name, audit in zip(CONTRACTS, NAMES, AUDITORS):
        evidence = _source(advanced.get(key), "studio.advanced." + key, base["source_digest"])
        result = audit(evidence)
        if result.name != name:
            raise QualityGateError("advanced studio gate does not match owner")
        gates.append(result.as_dict())
        findings.extend(f.as_dict() for f in result.findings)
    return {
        "schema": "game.candidate.advanced_studio.v1",
        "source_digest": base["source_digest"],
        "candidate_passed": not findings,
        "release_certified": False,
        "gates": gates,
        "findings": findings,
        "evidence_digest": _digest(gates),
    }


def verify_advanced_studio(bundle: Mapping[str, Any], report: Mapping[str, Any]) -> dict:
    """Reconstruct all 34 source audits; caller cannot substitute a passing report."""
    actual = audit_advanced_studio(bundle)
    if not isinstance(report, Mapping) or dict(report) != actual:
        raise QualityGateError("independent 34-plane audit rejected unsupported claim")
    attestation = {
        "schema": "game.studio.advanced_independent_review.v1",
        "source_digest": actual["source_digest"],
        "gate_count": len(actual["gates"]),
        "candidate_passed": actual["candidate_passed"],
        "release_certified": False,
        "source_recomputation": True,
    }
    return {**attestation, "receipt_digest": _digest(attestation)}
